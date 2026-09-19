# 🚀 Deploying CareRAG for free

This guide deploys CareRAG at **$0**. The stack uses:
- **Supabase** — free managed Postgres database (with pgvector)
- **Google Gemini** — free API for both embeddings and answers (no local model, so it fits small
  free hosts)
- **Render** (for the API) and/or **Streamlit Community Cloud** (for the chat UI)

> **Why not one single service?** CareRAG has two parts: a FastAPI backend and a Streamlit UI.
> Free hosts run one process each, so you have two easy options:
>
> - **Option A (recommended, simplest UI):** deploy the **direct-mode UI**
>   (`ui/streamlit_direct.py`) on **Streamlit Community Cloud**. It calls the RAG functions
>   in-process, so it needs **no separate backend** — one free service, one public chat URL.
> - **Option B (API + UI split):** deploy the FastAPI backend on **Render** (start command
>   `uvicorn app.main:app --host 0.0.0.0 --port $PORT`) and the HTTP UI (`ui/streamlit_app.py`)
>   separately, pointed at the Render API URL.
>
> Both are free. Parts 1–2 (Supabase + Gemini) are shared by both. See the two deployment
> sections after Part 2.

---

## Part 1 — Database on Supabase (free)

If you already set up Supabase during local development, reuse it and skip to Part 2.

1. Go to https://supabase.com and sign in (GitHub login is easiest).
2. **New project** → give it a name (e.g. `carerag`).
3. Set a **database password** using **only letters and numbers** (avoid symbols — they break
   connection strings). Save it somewhere safe.
4. Pick the region closest to you, then wait ~2 minutes for it to provision.
5. Get your connection string: **Project Settings → Database → Connection string → URI**.
   - Prefer the **Session pooler** URI (host contains `pooler.supabase.com`). It's reliable over
     IPv4, unlike the direct `db.xxxx.supabase.co` host.
   - It looks like:
     `postgresql://postgres.abcxyz:YOUR-PASSWORD@aws-0-region.pooler.supabase.com:5432/postgres`
   - **Remove any `?pgbouncer=true`** (or other `?...`) at the end — the Python driver rejects it.
   - Replace `YOUR-PASSWORD` with your real password.

Keep this string private — it's your `DATABASE_URL`.

---

## Part 2 — Gemini API key(s) (free)

1. Go to https://aistudio.google.com/app/apikey and sign in with your Google account.
2. Click **Create API key** (no credit card needed). Copy it.
3. (Optional) Create up to **5 keys** to enable rotation. Even **1 key** works.

These become `GEMINI_API_KEY_1` … `GEMINI_API_KEY_5`.

---

## Part 3 — Push your code to GitHub

1. Create a new GitHub repository (public is fine — `.env` is git-ignored, so no secrets leak).
2. Push your project:
   ```bash
   git init
   git add .
   git commit -m "CareRAG"
   git branch -M main
   git remote add origin https://github.com/<you>/carerag.git
   git push -u origin main
   ```
3. Double-check `.env` is NOT in the repo (it should be ignored by `.gitignore`).

---

## Part 4 — Deploy to Hugging Face Spaces (free)

### 4.1 Create the Space
1. Go to https://huggingface.co and sign in.
2. **New Space** → choose:
   - **SDK: Docker** (gives us full control to run both processes)
   - **Hardware:** the free CPU tier
3. Note the Space's Git URL.

### 4.2 Add the files the Space needs

Create these two files in your repo (they tell the Space how to run):

**`Dockerfile`**
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create the tables, then start BOTH the API and the UI.
# The API runs on 8000 (internal); Streamlit is exposed on 7860 (HF default port).
ENV API_BASE_URL=http://localhost:8000
EXPOSE 7860
CMD python -m app.database && \
    (uvicorn app.main:app --host 0.0.0.0 --port 8000 &) && \
    streamlit run ui/streamlit_app.py --server.port 7860 --server.address 0.0.0.0
```

> The UI's `API_BASE_URL` is already `http://localhost:8000`, which matches the backend inside the
> same container.

### 4.3 Add your secrets to the Space (NOT in code)
In the Space: **Settings → Variables and secrets → New secret**. Add:
- `DATABASE_URL` = your Supabase Session-pooler URI (no `?pgbouncer=true`)
- `GEMINI_API_KEY_1` = your Gemini key (add `_2`…`_5` if you have more)
- `SIMILARITY_THRESHOLD` = `0.8`

These become environment variables the app reads via `config.py` — the same way `.env` works
locally, but stored securely in the Space instead of a file.

### 4.4 Push and let it build
Push your repo (including the new `Dockerfile`) to the Space's Git remote (or connect the GitHub
repo). Hugging Face builds the image and starts it. First build takes a few minutes (it downloads
the embedding model once).

When it's live, open the Space URL — that's your public CareRAG demo. 🎉

---

## Troubleshooting

| Symptom | Likely cause / fix |
|--------|--------------------|
| `password authentication failed` | Wrong password, or symbols in it. Reset to letters+numbers. |
| `invalid URI query parameter "pgbouncer"` | Remove `?pgbouncer=true` from `DATABASE_URL`. |
| `vector type not found` | First run must create the extension — `python -m app.database`. |
| Answers always say "I don't know" | `SIMILARITY_THRESHOLD` too low. Set it to `0.8` and restart. |
| Model download slow on first request | Normal — the embedding model (~90 MB) downloads once at startup. |
| Space sleeps / slow first load | Free tier sleeps when idle; it wakes on the next visit. Expected. |

---

## Cost summary

| Service | Tier | Cost |
|---------|------|------|
| Supabase | Free (500 MB DB) | $0 |
| Gemini API | Free tier | $0 |
| Embeddings | Runs locally in the app | $0 |
| Hugging Face Spaces | Free CPU | $0 |
| **Total** | | **$0** |


---

## Deploy the chat UI on Streamlit Community Cloud (Option A — recommended)

This deploys `ui/streamlit_direct.py`, which runs everything in one process (no separate API).

1. Push your code to GitHub (Part 3 above), including `ui/streamlit_direct.py`.
2. Go to https://share.streamlit.io and sign in with GitHub (free, no card).
3. **Create app** → pick your repo and branch → set **Main file path** to:
   ```
   ui/streamlit_direct.py
   ```
4. Open **Advanced settings → Secrets** and paste your secrets in TOML form:
   ```toml
   DATABASE_URL = "postgresql://postgres.xxx:PASSWORD@aws-0-region.pooler.supabase.com:5432/postgres"
   GEMINI_API_KEY_1 = "your-gemini-key"
   SIMILARITY_THRESHOLD = "0.8"
   ```
   (Streamlit Cloud exposes these as environment variables, which `app/config.py` reads — same as
   a local `.env`.)
5. Click **Deploy**. First build takes a few minutes. You'll get a public URL like
   `https://your-app.streamlit.app` — that's your live CareRAG chat. 🎉

> Because we use the Gemini embedding API (not a local PyTorch model), the app is lightweight and
> fits Streamlit Community Cloud's free resources comfortably.

---

## Deploy the API on Render (Option B — API + /docs)

1. Push to GitHub. On https://render.com create a **New Web Service** from your repo.
2. **Build command:** `pip install -r requirements.txt`
3. **Start command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Add environment variables: `DATABASE_URL`, `GEMINI_API_KEY_1`, `SIMILARITY_THRESHOLD=0.8`.
5. `runtime.txt` pins Python 3.11 (required — newer Python lacks some pinned wheels).
6. Deploy. Your API is at `https://<name>.onrender.com` (`/` health check, `/docs` interactive docs).

> The free Render tier has 512 MB RAM and sleeps when idle. Thanks to Gemini embeddings (no torch),
> the app fits within 512 MB.
