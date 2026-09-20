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
> - **Option B (API service):** deploy the FastAPI backend on **Render** (start command
>   `uvicorn app.main:app --host 0.0.0.0 --port $PORT`) to expose CareRAG as an HTTP API with
>   interactive `/docs`.
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

## Part 4 — Deploy the app (free)

> **Note on Hugging Face Spaces:** this project originally planned to use HF Spaces, but HF now
> requires a **paid (PRO)** plan for compute Spaces (only Static — which can't run Python — stays
> free). So we deploy on **Streamlit Community Cloud** and/or **Render** instead. Both are free and
> run Python. See the two "Deploy the ..." sections at the end of this document:
>
> - **Deploy the chat UI on Streamlit Community Cloud (Option A — recommended)** — one process, the
>   full app, a public chat URL.
> - **Deploy the API on Render (Option B)** — the FastAPI backend with `/docs`.

---

## Troubleshooting

| Symptom | Likely cause / fix |
|--------|--------------------|
| `password authentication failed` | Wrong password, or symbols in it. Reset to letters+numbers. |
| `invalid URI query parameter "pgbouncer"` | Remove `?pgbouncer=true` from `DATABASE_URL`. |
| `vector type not found` | First run must create the extension — `python -m app.database`. |
| Answers always say "I don't know" | `SIMILARITY_THRESHOLD` too low. Set it to `0.8` and restart. |
| Out of memory on startup | You're using the old local embeddings. This project uses the Gemini embedding API (no torch) — make sure you're on the latest code. |
| App sleeps / slow first load | Free tiers (Render/Streamlit Cloud) sleep when idle; they wake on the next visit. Expected. |

---

## Cost summary

| Service | Tier | Cost |
|---------|------|------|
| Supabase | Free (500 MB DB) | $0 |
| Gemini API (embeddings + answers) | Free tier | $0 |
| Streamlit Community Cloud (UI) | Free | $0 |
| Render (API, optional) | Free tier | $0 |
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
