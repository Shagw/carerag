# CareRAG – Healthcare Policy Assistant

## Project Plan & Learning Guide

This document explains **what** we are building, **why** each piece exists, and **how** it all
fits together. It is written so that a beginner can follow every step. Read this top to bottom
before touching any code.

---

## 1. What are we building? (The big picture)

We are building an assistant that can **answer questions about healthcare documents**.

Imagine you have a stack of PDFs: an insurance policy, a hospital discharge summary, some FAQs.
You do not want to read 80 pages to find out "What is the claim submission deadline?".

CareRAG lets you:

1. **Upload** those PDFs.
2. **Ask** a question in plain English.
3. Get back an **answer** plus a **citation** — the exact document and page the answer came from.

If the documents do not contain the answer, the assistant says **"I don't know"** instead of
making something up. This honesty is the single most important feature.

---

## 2. What is RAG? (The core concept)

RAG = **Retrieval-Augmented Generation**. It has three words, let's break them down:

- **Generation** — a Large Language Model (LLM, like GPT or Gemini) writes an answer.
- **Retrieval** — before the LLM writes anything, we *retrieve* the most relevant chunks of your
  documents.
- **Augmented** — we *augment* (feed) the LLM's prompt with those retrieved chunks.

Why not just ask the LLM directly? Because the LLM has never seen *your* private policy PDF.
And if we ask it anyway, it may invent a plausible-sounding but wrong answer ("hallucination").

RAG solves this: we only let the LLM answer using text we actually pulled from your documents,
and we can point to exactly where that text came from.

### The RAG flow in one picture

```
             ┌─────────────────────────────────────────────────────┐
   UPLOAD    │  PDF ──► extract text ──► split into chunks ──►      │
   (once)    │  turn each chunk into an embedding (a vector) ──►    │
             │  store chunk + vector in PostgreSQL (pgvector)       │
             └─────────────────────────────────────────────────────┘

             ┌─────────────────────────────────────────────────────┐
   ASK       │  question ──► turn question into an embedding ──►    │
   (many     │  find the closest chunks in the database ──►         │
    times)   │  send question + those chunks to the LLM ──►         │
             │  LLM writes an answer + we attach the source pages   │
             └─────────────────────────────────────────────────────┘
```

---

## 3. Key terms (plain-English glossary)

| Term | Plain meaning |
|------|---------------|
| **Embedding** | A list of numbers (a "vector") that represents the *meaning* of a piece of text. Similar meanings produce similar numbers. |
| **Vector similarity search** | Finding stored text whose meaning is closest to the question, by comparing vectors. |
| **Chunk** | A small slice of a document (e.g. ~500 words). We split big PDFs into chunks so we can find just the relevant part. |
| **pgvector** | A PostgreSQL extension that lets the database store vectors and find the nearest ones quickly. |
| **Citation** | The document name + page number where an answer came from. |
| **LLM** | Large Language Model — the AI that writes the final answer text. |

---

## 4. The technology stack (FINAL — everything is 100% free)

This project is a CV/portfolio piece, so a hard rule is: **it must cost $0** — no paid APIs,
no paid hosting, no credit card. Here is the locked-in free stack and why each piece was chosen.

| Layer | Tool | Why (and why it's free) |
|-------|------|-------------------------|
| API / backend | **FastAPI** (Python) | Fast to write, automatic interactive docs at `/docs`, great for beginners. |
| Database | **Supabase Postgres + pgvector** | Free tier Postgres with the pgvector extension already available. One tool for storage + vector search. |
| PDF reading | **PyMuPDF** | Extracts text *and* tells us the page number of each piece of text (needed for citations!). |
| Embeddings | **Local `sentence-transformers` (`all-MiniLM-L6-v2`, 384 dims)** | Runs *inside* our own app — no API key, no cost, no daily limit, works offline. ~90 MB model, CPU only. |
| Answer generation | **Google Gemini `gemini-1.5-flash`** | Google's free-tier API. Free key from aistudio.google.com, no credit card. Only used for writing the final answer text. |
| UI | **Streamlit** | Simplest possible chat UI in pure Python. No React/JS needed. Great for a 2-day build. |
| Deploy | **Hugging Face Spaces** (free) | Free container (16 GB RAM) that can host the app. One public URL to put on your CV. |
| Packaging | **Docker** (optional) | Makes it run anywhere the same way. Only if time permits. |

> **Why Streamlit over React?** Saves ~a full day of frontend work. The instructions allow either.
>
> **Why local embeddings?** "Local" means the tiny model runs inside our own Python process
> wherever the app is deployed — not just on the laptop. No API key, no per-call cost, and search
> keeps working even if the Gemini free quota runs out. See `ARCHITECTURE.md` §6 for how this works
> when deployed.
>
> **Key rule:** the *same* embedding model must be used to store documents AND to search questions,
> otherwise the vectors are not comparable. We use local `all-MiniLM-L6-v2` for both.

---

## 5. Project folder structure

```
carerag/
├── PLAN.md                  ← this document
├── README.md                ← how to run it (written last)
├── ARCHITECTURE.md          ← diagram + explanation
├── DEPLOYMENT.md            ← free hosting steps (Supabase + HF Spaces)
├── .env.example             ← TEMPLATE for secrets (names + placeholders only)
├── .env                     ← YOUR real secrets — you create it, never committed
├── .gitignore               ← ensures .env is never pushed to GitHub
├── requirements.txt         ← Python dependencies
│
├── app/                     ← the backend (FastAPI)
│   ├── __init__.py
│   ├── main.py              ← FastAPI app + routes (upload, ask, documents, history)
│   ├── config.py            ← reads settings from environment (.env)
│   ├── database.py          ← connects to Supabase Postgres, creates tables
│   ├── models.py            ← the shapes of data (Pydantic request/response)
│   ├── pdf_utils.py         ← extract text + page numbers from PDF (PyMuPDF)
│   ├── chunking.py          ← split text into overlapping chunks
│   ├── embeddings.py        ← turn text into vectors (LOCAL sentence-transformers)
│   ├── vector_store.py      ← save chunks & run similarity search (pgvector)
│   ├── key_manager.py       ← rotates up to 5 Gemini API keys with cooldown
│   ├── llm.py               ← call Gemini to generate the answer (uses key_manager)
│   └── rag.py               ← the RAG pipeline: retrieve → prompt → answer → cite
│
├── ui/
│   └── streamlit_app.py     ← the chat interface (upload, chat, citations, doc list)
│
└── sample_docs/             ← example PDFs to test with
```

Each file does **one job**. This keeps every file short and easy to read.

> **Security rule (agreed):** the `.env` file holding your real Supabase URL and Gemini keys is
> **yours alone**. It is never read, edited, printed, or committed by the assistant. Only
> `.env.example` (a placeholder template) is created, and `.env` is listed in `.gitignore`.

---

## 6. The database design

We support **multiple documents**, and every question searches **across all of them**. Three tables:

**`documents`** — one row per uploaded PDF.
```
id            (unique id)
filename      (original file name — shown in citations)
uploaded_at   (timestamp)
```

**`chunks`** — many rows per document (one per chunk of text).
```
id            (unique id)
document_id   (which document this chunk belongs to → the filename for citations)
page_number   (which page it came from — THIS enables page citations)
content       (the actual text of the chunk — also shown as the citation snippet)
embedding     (the vector, type: vector(384))   ← 384 because all-MiniLM-L6-v2 outputs 384 numbers
```

**`conversations`** — chat history AND follow-up memory.
```
id            (unique id)
session_id    (groups messages of one chat, so follow-up questions have context)
question      (what the user asked)
answer        (what we replied)
sources       (JSON: which document + page + snippet we cited)
created_at    (timestamp)
```

Because it's **multiple documents**, supporting them is almost free: upload just adds more rows to
`chunks`, and search naturally looks across every chunk regardless of document. The citation carries
the document name so the user sees exactly which file (and page) each answer came from.

The magic query is: *"give me the 5 chunks whose `embedding` is closest to the question's
embedding"*. pgvector does this with the `<=>` (cosine distance) operator. Smaller distance = closer
meaning.

---

## 7. Day-by-day task plan

> Prerequisites (you do these once, I give exact steps): install latest Python, create a free
> Supabase project (get the database connection string), get 1–5 free Gemini API keys.

### Day 1 — Ingestion pipeline (get documents INTO the system)

- [ ] 1.1 Create `requirements.txt`, `.env.example`, `.gitignore`, `config.py`
- [ ] 1.2 Connect to Supabase Postgres + create tables (`database.py`) — no Docker
- [ ] 1.3 `pdf_utils.py`: extract text with page numbers (max 10 MB, text PDFs)
- [ ] 1.4 `chunking.py`: split text into overlapping chunks (keep page numbers)
- [ ] 1.5 `embeddings.py`: local `all-MiniLM-L6-v2` encoder (384-dim vectors)
- [ ] 1.6 `vector_store.py`: save chunks + vectors to DB
- [ ] 1.7 FastAPI `POST /upload` (multiple files) wiring it all together
- [ ] 1.8 `vector_store.py`: cosine-similarity search across ALL documents
- [ ] 1.9 Test: upload a sample PDF, confirm chunks in DB

### Day 2 — Answering pipeline (get ANSWERS out of the system)

- [ ] 2.1 `key_manager.py`: rotate up to 5 Gemini keys, cooldown when rate-limited
- [ ] 2.2 `llm.py`: call Gemini `gemini-1.5-flash` (uses `key_manager`)
- [ ] 2.3 `rag.py`: retrieve → build prompt (with chat history) → answer → citations
- [ ] 2.4 Add the **strict** "I don't know" guardrail
- [ ] 2.5 FastAPI `POST /ask` + `GET /documents` + `DELETE /documents/{id}`
- [ ] 2.6 Save Q&A to `conversations` (history + follow-up memory)
- [ ] 2.7 `streamlit_app.py`: chat UI + upload + document list + collapsible citations
- [ ] 2.8 Write `README.md`, `DEPLOYMENT.md`, add sample docs
- [ ] 2.9 (Optional) Docker packaging + final end-to-end test

### Key rotation (feature detail)

We keep up to **5 Gemini API keys**. `key_manager.py` hands out an available key. When a key hits a
rate-limit / quota error, we mark it "cooling down" for a set time and switch to the next key. We do
**not** reuse a cooling-down key until its cooldown passes. If **all 5** are cooling down at once, the
API returns a friendly message: *"All AI keys are cooling down, please try again in a minute."*

### Conversation memory (feature detail)

Each chat has a `session_id`. When answering a new question, we include the last few Q&A turns from
that session in the prompt, so follow-ups like *"and what about for children?"* are understood in
context. History is also stored so it can be viewed later.

---

## 8. How citations will work (the star feature)

Because PyMuPDF gives us the page number when we extract text, every chunk we store remembers
its page. When we retrieve chunks to answer a question, we already know:

- which **document** each chunk came from, and
- which **page** it was on.

So the final answer will look like this — note the **quoted snippet** under each source (Option B):

```
Answer: A pre-authorization is required for all planned hospitalizations,
and must be requested at least 48 hours in advance.

Sources:
  • policy.pdf — page 12
      "Pre-authorization is mandatory for all planned hospitalizations and
       must be requested at least 48 hours prior to admission."
  • policy.pdf — page 13
      "Emergency admissions must be intimated within 24 hours."
```

The quoted snippet is the actual chunk text we retrieved — we already have it (we fed it to the LLM),
so showing it costs nothing and proves the answer is grounded in the real document, not invented. In
the UI the snippet sits in a **collapsible box** so the screen stays tidy.

If none of the retrieved chunks are relevant enough, we return (strict guardrail):

```
Answer: I don't know based on the provided documents.
```

We decide "not relevant enough" using the similarity score from pgvector: if even the closest chunk's
cosine distance is above a threshold, we skip the LLM and return "I don't know".

---

## 9. How you will run it (preview)

No local database or Docker needed — we use the free **Supabase** cloud Postgres.

```bash
# 1. Install python deps (into a virtual environment)
pip install -r requirements.txt

# 2. Create your own .env from the template and fill in YOUR secrets
#    (Supabase DATABASE_URL + 1-5 Gemini keys). You do this privately;
#    the assistant never reads or edits .env.
cp .env.example .env

# 3. Create the database tables (one-time)
python -m app.database

# 4. Start the API
uvicorn app.main:app --reload

# 5. Start the UI (in another terminal)
streamlit run ui/streamlit_app.py
```

Then open the Streamlit page, upload PDFs, and ask questions.

---

## 10. What we build first

We follow the Day 1 list in order. Each code file will have **heavy comments** explaining
every line, because the goal is for you to understand it, not just run it.

Next step: confirm this plan, then I'll scaffold the folder and start with `requirements.txt`
and the database setup.
