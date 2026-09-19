# CareRAG – Architecture

This document shows how the pieces connect. Pair it with `PLAN.md` (which explains the concepts).

---

## 1. High-level architecture diagram

```
 ┌──────────────────────────────────────────────────────────────────────────┐
 │                              USER (browser)                                │
 │              Streamlit chat UI — upload, chat, doc list, citations         │
 └───────────────┬───────────────────────────────────┬────────────────────────┘
                 │ upload PDF(s)                       │ ask question
                 ▼                                     ▼
 ┌──────────────────────────────────────────────────────────────────────────┐
 │                            FastAPI backend                                 │
 │                                                                            │
 │   POST /upload                         POST /ask                           │
 │   ┌───────────────────────┐            ┌────────────────────────────────┐ │
 │   │ 1. read PDF (PyMuPDF) │            │ 1. embed question (LOCAL model)│ │
 │   │ 2. chunk text         │            │ 2. vector search top-k chunks  │ │
 │   │ 3. embed each chunk   │            │ 3. strict "I don't know" guard │ │
 │   │    (LOCAL model)      │            │ 4. build prompt (+ chat history)│ │
 │   │ 4. store in DB        │            │ 5. Gemini writes answer        │ │
 │   └───────────┬───────────┘            │ 6. attach citations + snippet  │ │
 │               │        embeddings run  │ 7. save to conversations       │ │
 │               │        IN-PROCESS      └───────────────┬────────────────┘ │
 │               │        (no network)                    │                   │
 └───────────────┼─────────────────────────────────────────┼──────────────────┘
                 │                                          │ uses key_manager
                 ▼                                          ▼ (rotates 5 keys)
 ┌──────────────────────────────┐            ┌───────────────────────────────┐
 │  Supabase Postgres + pgvector │            │   Google Gemini API           │
 │  ┌────────────┐ ┌───────────┐ │            │   gemini-1.5-flash            │
 │  │ documents  │ │  chunks   │ │            │   (answer text only)          │
 │  │            │ │+vector(384)│ │            │                               │
 │  └────────────┘ └───────────┘ │            │   free tier, up to 5 keys     │
 │  ┌──────────────┐             │            │   with cooldown rotation      │
 │  │conversations │  (history)  │            └───────────────────────────────┘
 │  └──────────────┘             │
 └──────────────────────────────┘

 NOTE: The embedding model (all-MiniLM-L6-v2) runs INSIDE the FastAPI process — it is NOT a
 separate service. Only the database (Supabase) and the answer LLM (Gemini) are remote.
```

---

## 2. The two pipelines

### Ingestion pipeline (POST /upload) — runs once per document, supports multiple files
```
PDF file(s)  (max 10 MB each, text-based)
  → pdf_utils.extract_pages()      # [(page_number, text), ...]
  → chunking.chunk_pages()         # [(page_number, chunk_text), ...]
  → embeddings.embed_texts()       # LOCAL model → [(chunk_text, vector384), ...]
  → vector_store.save_chunks()     # INSERT into documents + chunks tables
```

### Query pipeline (POST /ask) — runs on every question
```
question (+ session_id for memory)
  → embeddings.embed_texts([question])   # LOCAL model → question vector
  → vector_store.search(vector, k=5)     # nearest chunks across ALL docs + distances
  → rag: strict guardrail                # if best distance too large → "I don't know", stop
  → rag.build_prompt(question, chunks,   # prompt with chunk text + recent chat history
                     history)
  → llm.generate(prompt)                 # Gemini answer (key_manager picks an available key)
  → rag: attach citations                # answer + [doc, page, snippet] list
  → save to conversations                # history + follow-up memory
```

---

## 3. Module responsibilities (one job each)

| Module | Input | Output | Responsibility |
|--------|-------|--------|----------------|
| `pdf_utils.py` | PDF bytes | list of (page_no, text) | extract text keeping page numbers |
| `chunking.py`  | (page_no, text) list | (page_no, chunk) list | split into overlapping chunks |
| `embeddings.py`| list of strings | list of 384-dim vectors | run the LOCAL sentence-transformers model |
| `vector_store.py` | chunks / query vector | DB writes / nearest chunks | all DB access for documents & chunks |
| `key_manager.py` | – | an available API key | rotate up to 5 Gemini keys, cooldown on limit |
| `llm.py` | prompt string | answer string | call Gemini (asks key_manager for a key) |
| `rag.py` | question, history | answer + citations | orchestrate retrieve→guard→prompt→answer→cite |
| `database.py` | – | connection/session | connect to Supabase + create tables |
| `config.py` | environment (.env) | settings object | central configuration |
| `models.py` | – | Pydantic models | request/response shapes |
| `main.py` | HTTP requests | HTTP responses | define API routes |

---

## 4. Why this structure is safe and clear

- **Each module has one responsibility** → easy to read and test individually.
- **Embeddings are local and isolated** in `embeddings.py`; **Gemini is isolated** in `llm.py`
  (+ `key_manager.py`) → the rest of the code does not care which provider is used.
- **All database SQL lives in `vector_store.py` / `database.py`** → one place to look.
- **Citations are guaranteed** because page number + chunk text travel from extraction all the way
  to the answer, so we can always show document + page + snippet.
- **Secrets stay in `.env`** (never committed); code only reads variable names via `config.py`.

---

## 5. Data flow for a single question (concrete example)

1. User asks: *"What is the claim submission deadline?"*
2. We embed that sentence with the LOCAL model → `[0.01, -0.23, ...]` (**384** numbers).
3. pgvector finds the 5 chunks with the smallest cosine distance across ALL uploaded documents.
4. Suppose the best chunk (distance 0.18) is from `policy.pdf` page 12 and says
   *"Claims must be submitted within 30 days of discharge."*
5. Strict guard: 0.18 is below our threshold → relevant, so we proceed (if it were too large we'd
   return "I don't know" without calling Gemini).
6. We put that chunk (and the others) + recent chat history into the prompt and ask Gemini to answer
   using only them.
7. Gemini replies: *"Claims must be submitted within 30 days of discharge."*
8. We attach the citation with snippet: `policy.pdf — page 12` + the quoted sentence.
9. We save the question, answer, and sources to `conversations` for history and follow-up memory.

---

## 6. How local embeddings work when deployed

"Local" does **not** mean "only your laptop". It means the embedding model runs *inside the app's own
Python process*, wherever that app runs.

```
Hugging Face Space (one free container, 16 GB RAM)
┌─────────────────────────────────────────────────────┐
│  FastAPI app process                                  │
│    model = SentenceTransformer("all-MiniLM-L6-v2")   │  ← downloaded once at startup (~90 MB)
│    vector = model.encode(text)                        │  ← runs here in RAM, CPU, free, no network
│         │                                              │
│         ▼ store / search vectors over the network      │
│   Supabase Postgres (pgvector)  ← the only remote data store
│                                                        │
│    answer = gemini.generate(prompt)  ← remote API call, only for the final answer text
└─────────────────────────────────────────────────────┘
```

- No embedding API key, no per-call cost, no daily limit for embeddings.
- The same model is used for both storing documents and searching questions, so vectors are
  comparable.
- Only two things are remote: the **database** (Supabase) and the **answer LLM** (Gemini).
