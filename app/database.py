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


# We cache ONE database connection and reuse it, because opening a new
# connection to Supabase costs ~2 seconds (network + TLS + vector-type lookup).
# Reconnecting on every query made switching/renaming chats very slow.
_cached_conn = None


class _SharedConnection:
    """
    A context manager wrapper around the shared connection.

    Callers use `with get_connection() as conn:` all over the codebase. If we
    returned the raw psycopg connection, that `with` block would CLOSE it on
    exit (psycopg behaviour) — destroying our cache and forcing a slow reconnect
    every call. This wrapper instead commits (or rolls back on error) at block
    exit but keeps the connection OPEN for reuse.
    """

    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn                     # give callers the real connection

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self._conn.commit()               # success -> save
        else:
            self._conn.rollback()             # error -> undo, but keep conn open
        return False                          # don't suppress exceptions

    # Let callers also use the object directly if they don't use `with`.
    def __getattr__(self, name):
        return getattr(self._conn, name)


def _open_new_connection(register_vector_type: bool):
    conn = psycopg.connect(settings.database_url)
    if register_vector_type:
        register_vector(conn)
    return conn


def get_connection(register_vector_type: bool = True):
    """
    Return the shared, reused database connection wrapped so `with` blocks
    commit but do NOT close it.

    Reusing one connection avoids paying the ~2s connect cost on every query.
    If the cached connection has been closed or has died, we open a fresh one.
    """
    global _cached_conn

    # Reuse the existing connection if it's still open and healthy.
    if _cached_conn is None or _cached_conn.closed:
        _cached_conn = _open_new_connection(register_vector_type)

    return _SharedConnection(_cached_conn)


def create_tables():
    """
    Create the pgvector extension and our 3 tables, if they don't exist yet.

    Running this more than once is safe: every statement uses
    "IF NOT EXISTS", so it won't complain or duplicate anything.
    """
    # Open a DEDICATED connection (not the shared cache) WITHOUT registering the
    # vector type yet — the "vector" type does not exist until CREATE EXTENSION
    # runs below. A dedicated connection avoids polluting the cache.
    conn = psycopg.connect(settings.database_url)
    try:
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

            # 6) chats table — the list of named chats (multi-chat workspace).
            #    A chat's `id` is the SAME value used as session_id on documents
            #    and conversations, so each chat has its own isolated documents,
            #    history, and search.
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS chats (
                    id         TEXT PRIMARY KEY,          -- the chat id (a UUID) = session_id elsewhere
                    owner_id   TEXT NOT NULL,             -- which owner (workspace) this chat belongs to
                    name       TEXT NOT NULL,             -- human-friendly name, e.g. "Health Policy"
                    created_at TIMESTAMP DEFAULT now(),
                    deleted_at TIMESTAMP                  -- set when SOFT-deleted; NULL = active
                );
                """
            )

            # If the chats table already existed WITHOUT owner_id (earlier
            # version), add it now. Existing chats get a placeholder owner.
            cur.execute(
                """
                ALTER TABLE chats
                ADD COLUMN IF NOT EXISTS owner_id TEXT NOT NULL DEFAULT 'legacy';
                """
            )

            # Add the soft-delete column if an older chats table lacks it.
            cur.execute(
                "ALTER TABLE chats ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP;"
            )

            # 7) owners table — a lightweight "who" for the multi-chat workspace.
            #    An owner = one browser/workspace. Its id (a UUID) is the key kept
            #    in the URL (?owner=...); the name is just a friendly label.
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS owners (
                    id         TEXT PRIMARY KEY,          -- the owner id (a UUID) — the real key
                    name       TEXT NOT NULL,             -- friendly display name (not unique)
                    created_at TIMESTAMP DEFAULT now()
                );
                """
            )

        # Save all the changes above to the database.
        conn.commit()
    finally:
        conn.close()

    print("Tables created (or already existed). Database is ready.")


# This block runs ONLY when you execute:  python -m app.database
# (It does NOT run when another file merely imports this one.)
if __name__ == "__main__":
    create_tables()
