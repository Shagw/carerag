# ============================================================================
# database.py — connects to the Supabase Postgres database and creates tables.
#
# This file has TWO jobs:
#   1. get_connection() ....... open a connection to the database
#   2. create_tables() ........ create our 3 tables (run once at setup)
#
# HOW YOU RUN THE SETUP (later, after prereqs are done):
#       python -m app.database
#   ...which triggers the code at the very bottom of this file.
# ============================================================================

# psycopg is the library that lets Python talk to a PostgreSQL database.
import psycopg

# This helper registers the "vector" type with psycopg, so Python and Postgres
# agree on how to send/receive the embedding vectors.
from pgvector.psycopg import register_vector

# Our single settings object, which holds the database_url from your .env.
from app.config import settings


def get_connection(register_vector_type: bool = True):
    """
    Open and return a new connection to the Supabase Postgres database.

    A "connection" is an open line to the database that we send SQL through.
    Whoever calls this function is responsible for closing it when done
    (we use `with get_connection() as conn:` elsewhere, which auto-closes).

    register_vector_type:
        Normally True — teaches psycopg about the pgvector "vector" type so we
        can pass Python lists of numbers directly as vectors.
        We pass False during first-time setup (create_tables), because the
        "vector" type does not exist yet until we run CREATE EXTENSION.
    """
    # Connect using the URL from .env (postgresql://user:pass@host:5432/postgres).
    conn = psycopg.connect(settings.database_url)

    # Only register the vector type if the caller asked for it AND the
    # extension already exists (i.e. normal app use, not first-time setup).
    if register_vector_type:
        register_vector(conn)

    return conn


def create_tables():
    """
    Create the pgvector extension and our 3 tables, if they don't exist yet.

    Running this more than once is safe: every statement uses
    "IF NOT EXISTS", so it won't complain or duplicate anything.
    """
    # Open a connection WITHOUT registering the vector type yet — the "vector"
    # type does not exist until we run CREATE EXTENSION a few lines below.
    with get_connection(register_vector_type=False) as conn:
        # A "cursor" is the object we use to send SQL commands.
        with conn.cursor() as cur:

            # 1) Turn on the pgvector extension so Postgres understands the
            #    "vector" data type. Supabase has it available; this enables it.
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")

            # Now that the extension exists, register the vector type on this
            # connection so the vector(768) column below is understood.
            conn.commit()          # save the CREATE EXTENSION first
            register_vector(conn)  # then it's safe to register the type

            # 2) documents table — one row per uploaded PDF.
            #    session_id groups documents by the browser session that
            #    uploaded them, so each visitor only sees their OWN documents.
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id          SERIAL PRIMARY KEY,       -- auto-numbered unique id
                    session_id  TEXT NOT NULL,            -- who uploaded it (per-session isolation)
                    filename    TEXT NOT NULL,            -- original file name (shown in citations)
                    uploaded_at TIMESTAMP DEFAULT now()   -- when it was uploaded
                );
                """
            )

            # If the documents table already existed WITHOUT session_id (from an
            # earlier version), add the column now. IF NOT EXISTS makes this safe
            # to run repeatedly. Existing rows get a placeholder session id.
            cur.execute(
                """
                ALTER TABLE documents
                ADD COLUMN IF NOT EXISTS session_id TEXT NOT NULL DEFAULT 'legacy';
                """
            )

            # 3) chunks table — many rows per document (one per text chunk).
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS chunks (
                    id          SERIAL PRIMARY KEY,
                    document_id INTEGER NOT NULL           -- which document this chunk belongs to
                                REFERENCES documents(id)
                                ON DELETE CASCADE,          -- delete a document -> its chunks go too
                    page_number INTEGER NOT NULL,          -- page it came from (for citations)
                    content     TEXT NOT NULL,             -- the chunk text (also the citation snippet)
                    embedding   vector(768)                -- the 768-number meaning vector (Gemini)
                );
                """
            )

            # NOTE ON SEARCH SPEED:
            # We intentionally do NOT create an approximate vector index
            # (like ivfflat) here. Such indexes must be "trained" on existing
            # rows, so building one on an empty table gives wrong/empty results.
            # For this project's data size, an EXACT search (scan all chunks) is
            # fast AND 100% accurate. If you ever store hundreds of thousands of
            # chunks, add an ivfflat/hnsw index AFTER data is loaded, e.g.:
            #   CREATE INDEX ON chunks USING hnsw (embedding vector_cosine_ops);

            # 5) conversations table — chat history + follow-up memory.
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id         SERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL,             -- groups messages of one chat
                    question   TEXT NOT NULL,             -- what the user asked
                    answer     TEXT NOT NULL,             -- what we replied
                    sources    JSONB,                     -- citations: doc + page + snippet
                    created_at TIMESTAMP DEFAULT now()
                );
                """
            )

        # Save all the changes above to the database.
        conn.commit()

    print("Tables created (or already existed). Database is ready.")


# This block runs ONLY when you execute:  python -m app.database
# (It does NOT run when another file merely imports this one.)
if __name__ == "__main__":
    create_tables()
