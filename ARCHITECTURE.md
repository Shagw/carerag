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
 │                       Backend logic (FastAPI or direct)                    │
 │                                                                            │
 │   upload flow                          ask flow                            │
 │   ┌───────────────────────┐            ┌────────────────────────────────┐ │
 │   │ 1. read PDF (PyMuPDF) │            │ 1. embed question (Gemini API) │ │
 │   │ 2. chunk text         │            │ 2. vector search top-k chunks  │ │
 │   │ 3. embed chunks       │            │ 3. strict "I don't know" guard │ │
 │   │    (Gemini API)       │            │ 4. build prompt (+ chat history)│ │
 │   │ 4. store in DB        │            │ 5. Gemini writes answer        │ │
 │   └───────────┬───────────┘            │ 6. attach citations + snippet  │ │
 │               │                        │ 7. save to conversations       │ │
 │               │                        └───────────────┬────────────────┘ │
 └───────────────┼─────────────────────────────────────────┼──────────────────┘
                 │                                          │ both use key_manager
                 ▼                                          ▼ (rotates up to 5 keys)
 ┌──────────────────────────────┐            ┌───────────────────────────────┐
 │  Supabase Postgres + pgvector │            │   Google Gemini API           │
 │  ┌────────────┐ ┌───────────┐ │            │  - gemini-embedding-001 (768) │
 │  │ documents  │ │  chunks   │ │            │    for embeddings             │
 │  │            │ │+vector(768)│ │            │  - gemini-flash-latest        │
 │  └────────────┘ └───────────┘ │            │    for answers                │
 │  ┌──────────────┐             │            │  free tier, up to 5 keys      │
 │  │conversations │  (history)  │            │  with cooldown rotation       │
 │  └──────────────┘             │            └───────────────────────────────┘
 └──────────────────────────────┘

 NOTE: Both embeddings AND answers use the remote Gemini API. The app itself is lightweight
 (no local ML model), so it fits small free hosts. Remote services: Supabase (DB) + Gemini (AI).

 DEPLOYMENT: the same backend logic runs two ways — as a FastAPI service (app/main.py, deployed on
 Render) OR called in-process by the Streamlit UI (ui/streamlit_direct.py, deployed on Streamlit
 Community Cloud). Both paths use the identical functions in vector_store / rag / embeddings / llm.
```

---

## 2. The two pipelines

### Ingestion pipeline (POST /upload) — runs once per document, supports multiple files
```
PDF file(s)  (max 10 MB each, text-based)
  → pdf_utils.extract_pages()      # [(page_number, text), ...]
  → chunking.chunk_pages()         # [(page_number, chunk_text), ...]
  → embeddings.embed_texts()      # Gemini API (batched) → 768-dim vectors
  → vector_store.save_chunks()     # INSERT into documents + chunks tables
```

### Query pipeline (POST /ask) — runs on every question
```
question (+ session_id for memory)
  → embeddings.embed_text(question)      # Gemini API → 768-dim question vector
  → vector_store.search(vector, k, sid)  # nearest chunks in THIS session's docs + distances
  → rag: strict guardrail                # if best distance too large → "I don't know", stop
  → rag.build_prompt(question, chunks,   # prompt with chunk text + recent chat history
                     history)
  → llm.generate(prompt)                 # Gemini answer (key_manager picks an available key)
  → rag: attach citations                # answer + [doc, page, snippet] list
  → save to conversations                # history + follow-up memory
```

> **Per-session isolation:** `search` filters `WHERE documents.session_id = sid` FIRST, then ranks
> by distance. So chunks from other sessions/chats are never candidates — you can only ever retrieve
> your own session's documents. (`session_id` is stored on the `documents` table; the UI keeps it in
> the page URL as `?session=...`.)

---

## 3. Module responsibilities (one job each)

| Module | Input | Output | Responsibility |
|--------|-------|--------|----------------|
| `pdf_utils.py` | PDF bytes | list of (page_no, text) | extract text keeping page numbers |
| `chunking.py`  | (page_no, text) list | (page_no, chunk) list | split into overlapping chunks |
| `embeddings.py`| list of strings | list of 768-dim vectors | call the Gemini embedding API (batched) |
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
- **Embeddings are isolated** in `embeddings.py` (Gemini embedding API); **answers are isolated** in
  `llm.py` (+ `key_manager.py`) → the rest of the code does not care which provider is used.
- **All database SQL lives in `vector_store.py` / `database.py`** → one place to look.
- **Citations are guaranteed** because page number + chunk text travel from extraction all the way
  to the answer, so we can always show document + page + snippet.
- **Secrets stay in `.env`** (never committed); code only reads variable names via `config.py`.

---

## 5. Data flow for a single question (concrete example)

1. User asks: *"What is the claim submission deadline?"*
2. We embed that sentence via the Gemini embedding API → `[0.01, -0.23, ...]` (**768** numbers).
3. pgvector finds the 5 chunks with the smallest cosine distance within THIS session's documents.
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

## 6. Why Gemini embeddings, and how it deploys

Originally CareRAG used a **local** embedding model (`all-MiniLM-L6-v2`) that ran inside the app's
own process. That was appealing (no API key, no per-call cost), but it depends on **PyTorch**, which
uses **~300+ MB of RAM**. On the free deployment host (Render, 512 MB limit) that caused an
**out-of-memory crash** on startup.

The fix was to switch embeddings to the **Gemini embedding API** (`gemini-embedding-001`, requested
at **768 dimensions**). The heavy PyTorch dependency is gone, so the app is small and deploys on free
tiers. Trade-off: embeddings now require a network call (and the free Gemini quota), but we batch all
of a document's chunks into **one** call to keep it fast.

```
Deployed app process (Streamlit Cloud OR Render — lightweight, no ML model)
┌─────────────────────────────────────────────────────┐
│  embeddings.embed_texts(chunks)  ── HTTPS ─▶ Gemini embedding API (768-dim)
│  llm.generate(prompt)            ── HTTPS ─▶ Gemini answer API
│  vector_store / conversations    ── SQL   ─▶ Supabase Postgres (pgvector)
└─────────────────────────────────────────────────────┘
```

**Two deployment shapes, same code:**
- **Streamlit Community Cloud** runs `ui/streamlit_direct.py`, which imports and calls the backend
  functions directly (one process, no HTTP). This is the deployed chat UI.
- **Render** (optional) runs `app/main.py` with uvicorn as a FastAPI service (gives `/docs`), for
  using CareRAG as an HTTP API.

**Key rule (unchanged):** the same embedding model must be used to store documents AND to search
questions, so vectors are comparable. We use `gemini-embedding-001` (768-dim) for both — with
`task_type=retrieval_document` when storing chunks and `retrieval_query` when embedding a question.
