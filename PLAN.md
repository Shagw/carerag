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
| Embeddings | **Google Gemini `gemini-embedding-001` (768 dims)** | Free-tier embedding API. Runs server-side, so our app stays tiny and fits small free hosts. |
| Answer generation | **Google Gemini `gemini-flash-latest`** | Google's free-tier API. Free key from aistudio.google.com, no credit card. Writes the final answer text. |
| UI | **Streamlit** | Simplest possible chat UI in pure Python. No React/JS needed. Great for a 2-day build. |
| Deploy | **Streamlit Community Cloud** (UI) + **Render** (API) | Both free, no credit card. One public chat URL for your CV. |

> **Why Streamlit over React?** Saves ~a full day of frontend work. The instructions allow either.
>
> **Why Gemini embeddings (not a local model)?** We originally used a local
> `sentence-transformers` model (no API key, runs in-process). But it pulls in **PyTorch (~300+ MB
> RAM)**, which **exceeded the 512 MB limit** of the free host (Render) and caused out-of-memory
> crashes. Switching to Gemini's embedding API removed that heavy dependency, so the app is
> lightweight and deploys for free. This is a real design trade-off we discovered during
> deployment — see the "Design evolution" note below.
>
> **Key rule:** the *same* embedding model must be used to store documents AND to search questions,
> otherwise the vectors are not comparable. We use Gemini `gemini-embedding-001` (768-dim) for both,
> with `task_type` set to `retrieval_document` when storing and `retrieval_query` when searching.

> **Design evolution (honest history):** the project first used local embeddings (384-dim
> `all-MiniLM-L6-v2`) and planned to deploy on Hugging Face Spaces. During deployment two things
> changed: (1) HF Spaces made compute tiers paid, so we moved the UI to **Streamlit Community Cloud**
> and the API to **Render**; (2) the local model's PyTorch dependency blew past Render's 512 MB free
> RAM, so we switched to the **Gemini embedding API (768-dim)**. The code, DB dimension, and these
> docs all reflect the final Gemini-based design.

---

## 5. Project folder structure

```
carerag/
├── PLAN.md                  ← this document
├── README.md                ← how to run it (written last)
├── ARCHITECTURE.md          ← diagram + explanation
├── DEPLOYMENT.md            ← free hosting steps (Supabase + Render/Streamlit Cloud)
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
│   ├── embeddings.py        ← turn text into vectors (Gemini embedding API, 768-dim)
│   ├── vector_store.py      ← save chunks & run similarity search (pgvector)
│   ├── key_manager.py       ← rotates up to 5 Gemini API keys with cooldown
│   ├── llm.py               ← call Gemini to generate the answer (uses key_manager)
│   └── rag.py               ← the RAG pipeline: retrieve → prompt → answer → cite
│
├── ui/
│   └── streamlit_direct.py  ← the chat interface (multi-chat, calls RAG in-process)
│
└── sample_docs/             ← example PDFs to test with
```

Each file does **one job**. This keeps every file short and easy to read.

> **Security rule (agreed):** the `.env` file holding your real Supabase URL and Gemini keys is
> **yours alone**. It is never read, edited, printed, or committed by the assistant. Only
> `.env.example` (a placeholder template) is created, and `.env` is listed in `.gitignore`.

---

## 6. The database design

We support **multiple documents**, and a question searches across all of them **within the same
browser session** (see per-session isolation below). Three tables:

**`documents`** — one row per uploaded PDF.
```
id            (unique id)
session_id    (which browser session uploaded it — enables per-session isolation)
filename      (original file name — shown in citations)
uploaded_at   (timestamp)
```

**`chunks`** — many rows per document (one per chunk of text).
```
id            (unique id)
document_id   (which document this chunk belongs to → the filename for citations)
page_number   (which page it came from — THIS enables page citations)
content       (the actual text of the chunk — also shown as the citation snippet)
embedding     (the vector, type: vector(768))   ← 768 because gemini-embedding-001 outputs 768 numbers
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

**`owners`** — a lightweight "who" for the multi-chat workspace (no passwords).
```
id            (a random UUID — the KEY, kept in the URL as ?owner=...)
name          (a friendly display label, e.g. "Saumya" — not unique, not a login)
created_at    (timestamp)
```

**`chats`** — the list of named conversations, each belonging to an owner.
```
id            (a UUID — ALSO used as the session_id for that chat's documents/history)
owner_id      (which owner/workspace this chat belongs to)
name          (e.g. "Health Policy")
created_at    (timestamp)
deleted_at    (SOFT DELETE: set when removed; NULL = active. Row is never physically deleted)
```

Because it's **multiple documents**, supporting them is almost free: upload just adds more rows to
`chunks`, and search looks across every chunk of the current session regardless of which document it
came from. The citation carries the document name so the user sees exactly which file (and page)
each answer came from.

The magic query is: *"give me the 5 chunks whose `embedding` is closest to the question's
embedding"*. pgvector does this with the `<=>` (cosine distance) operator. Smaller distance = closer
meaning.

### Per-session document isolation (privacy)

Every uploaded document is tagged with a `session_id` (the id of the browser session that uploaded
it). Three functions filter by it:

- `save_chunks(filename, chunks, session_id)` — stores the document under that session.
- `search(query_vector, top_k, session_id)` — its SQL has `WHERE documents.session_id = %s`, so the
  database **discards every chunk from other sessions BEFORE ranking by distance**. A chunk from a
  different chat is never even a candidate.
- `list_documents(session_id)` — only lists that session's documents.

So there are **two separate ideas** at query time, and they run in this order:
1. **`session_id` filter (the WHERE clause)** decides *whose* documents are eligible — a hard
   boundary. You can never retrieve another session's chunk.
2. **cosine distance (the ORDER BY)** decides *which* of the eligible chunks match best by meaning.

The `session_id` lives in the page URL (`?session=...`) so a refresh keeps the same session. This is
a no-login demo, so the isolation is convenience/privacy between sessions, not hard security —
someone with your exact session URL could load it. That trade-off is documented in the README.

### Multi-chat workspaces (owners + named conversations)

On top of per-document isolation, the app groups everything into **workspaces**:

- A visitor enters a **name** → we create an **owner** with a random UUID `id`, kept in the URL as
  `?owner=...`. The id is the real key; the name is just a label. A fresh browser / incognito with no
  owner id gets the name prompt and a brand-new empty workspace.
- An owner has many **chats** (conversations). `list_chats(owner_id)` shows only that owner's chats.
- Each chat's `id` **is** the `session_id` used for its documents and history — so every conversation
  is its own isolated knowledge base automatically. Uploading in chat A never affects chat B.

### Soft delete

Deleting a conversation is a **soft delete**: `delete_chat(id)` sets `chats.deleted_at = now()`
instead of removing the row. `list_chats` only returns rows where `deleted_at IS NULL`, so the chat
disappears from the user's list, but the row — and its documents and history — stay in the database.
This keeps deletions reversible (clear `deleted_at`) and preserves data for audit/recovery, which is
good practice for a healthcare-oriented app.

### Scope check (healthcare/insurance documents only)

CareRAG is meant for health/insurance documents, so on upload we reject unrelated files (e.g. a
résumé). After extracting the text, `pdf_utils._looks_like_health_or_insurance()` counts how many
DISTINCT terms from a curated list (`insurance`, `policy`, `claim`, `premium`, `hospital`,
`diagnosis`, `discharge`, `reimbursement`, …) appear. If fewer than **3** distinct terms are found,
`extract_pages` raises a `ValueError` with a friendly message, which the UI shows to the user. A real
policy/bill hits many terms; an unrelated document hits ~0. This is a simple, free, transparent check
(no extra API call); the term list and threshold are easy to tune.

---

## 7. Day-by-day task plan

> Prerequisites (you do these once, I give exact steps): install latest Python, create a free
> Supabase project (get the database connection string), get 1–5 free Gemini API keys.

### Day 1 — Ingestion pipeline (get documents INTO the system)

- [ ] 1.1 Create `requirements.txt`, `.env.example`, `.gitignore`, `config.py`
- [ ] 1.2 Connect to Supabase Postgres + create tables (`database.py`) — no Docker
- [ ] 1.3 `pdf_utils.py`: extract text with page numbers (max 10 MB, text PDFs)
- [ ] 1.4 `chunking.py`: split text into overlapping chunks (keep page numbers)
- [ ] 1.5 `embeddings.py`: Gemini `gemini-embedding-001` encoder (768-dim vectors)
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

# 5. Start the UI (single process — no separate API needed)
streamlit run ui/streamlit_direct.py
```

Then open the Streamlit page, upload PDFs, and ask questions.

---

## 10. What we build first

We follow the Day 1 list in order. Each code file will have **heavy comments** explaining
every line, because the goal is for you to understand it, not just run it.

Next step: confirm this plan, then I'll scaffold the folder and start with `requirements.txt`
and the database setup.
