# ============================================================================
# vector_store.py — all database work for documents, chunks, and search.
#
# Two main jobs:
#   1. save_chunks(filename, chunks) .... store an uploaded document + its chunks
#   2. search(query_vector, top_k) ...... find the chunks closest in meaning
#
# This is the bridge between our text pipeline (pdf -> chunks -> vectors) and
# the Supabase Postgres database (with the pgvector extension).
# ============================================================================

from typing import List, Tuple, Dict, Any

# Open a DB connection (this version registers the vector type, which we need
# both to store vectors and to search them).
from app.database import get_connection

# Turn chunk text into 384-number vectors.
from app.embeddings import embed_texts


def save_chunks(filename: str, chunks: List[Tuple[int, str]], session_id: str) -> int:
    """
    Save one uploaded document and all of its chunks to the database.

    INPUT:
        filename:   the original PDF name, e.g. "policy.pdf" (shown in citations).
        chunks:     list of (page_number, chunk_text) from chunking.chunk_pages().
        session_id: which browser session uploaded this (for per-session
                    isolation — each visitor only sees their own documents).

    OUTPUT:
        The new document's id (an integer). Handy for confirmations/tests.

    STEPS:
        1. Insert a row into `documents` (with its session_id), get its new id.
        2. Embed every chunk's text (in one batch — faster).
        3. Insert one row per chunk into `chunks`, carrying the embedding.
    """
    # Separate the (page, text) pairs into two parallel lists.
    # page_numbers[i] goes with texts[i].
    page_numbers = [page for (page, _text) in chunks]
    texts = [text for (_page, text) in chunks]

    # Turn all chunk texts into vectors at once (batch is faster than one-by-one).
    embeddings = embed_texts(texts)

    with get_connection() as conn:
        with conn.cursor() as cur:

            # 1) Insert the document row (with session_id) and get its new id.
            #    "RETURNING id" makes Postgres hand us the id it just created.
            cur.execute(
                "INSERT INTO documents (session_id, filename) VALUES (%s, %s) RETURNING id;",
                (session_id, filename),
            )
            document_id = cur.fetchone()[0]

            # 2) Insert every chunk. We loop over the three parallel lists
            #    together using zip(): (page, text, embedding) each time.
            for page_number, content, embedding in zip(page_numbers, texts, embeddings):
                cur.execute(
                    """
                    INSERT INTO chunks (document_id, page_number, content, embedding)
                    VALUES (%s, %s, %s, %s);
                    """,
                    (document_id, page_number, content, embedding),
                )

        # Save everything to the database.
        conn.commit()

    return document_id


def search(query_vector: List[float], top_k: int, session_id: str) -> List[Dict[str, Any]]:
    """
    Find the `top_k` chunks whose meaning is closest to the question vector,
    searching ONLY within the given session's documents.

    INPUT:
        query_vector: the embedded question (384 numbers).
        top_k:        how many nearest chunks to return.
        session_id:   only search documents uploaded by this session.

    OUTPUT:
        A list of dicts, each like:
            {
              "filename": "policy.pdf",     # which document (for the citation)
              "page_number": 12,            # which page (for the citation)
              "content": "the chunk text",  # used both for the LLM and the snippet
              "distance": 0.18              # cosine distance (smaller = closer)
            }
        Sorted from closest (smallest distance) to farthest.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            # The key query:
            #   chunks.embedding <=> %s   -> cosine DISTANCE between each stored
            #                                chunk and the question vector.
            #   WHERE documents.session_id = %s -> only THIS session's documents.
            #   ORDER BY that distance    -> closest first.
            #   LIMIT top_k               -> keep only the best few.
            cur.execute(
                """
                SELECT
                    documents.filename,
                    chunks.page_number,
                    chunks.content,
                    chunks.embedding <=> %s::vector AS distance
                FROM chunks
                JOIN documents ON documents.id = chunks.document_id
                WHERE documents.session_id = %s
                ORDER BY distance
                LIMIT %s;
                """,
                (query_vector, session_id, top_k),
            )
            rows = cur.fetchall()

    # Turn each raw row (a tuple) into a friendly dictionary.
    results: List[Dict[str, Any]] = []
    for filename, page_number, content, distance in rows:
        results.append(
            {
                "filename": filename,
                "page_number": page_number,
                "content": content,
                "distance": float(distance),
            }
        )

    return results


def list_documents(session_id: str) -> List[Dict[str, Any]]:
    """
    Return the documents uploaded by THIS session, with each one's chunk count.

    Used by the UI to show the user what's in THEIR knowledge base
    (per-session isolation — they never see other people's documents).
    Output: [{ "id": 2, "filename": "policy.pdf", "chunk_count": 4 }, ...]
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            # LEFT JOIN + COUNT gives each document its number of chunks.
            # WHERE filters to this session; GROUP BY collapses to one row per doc.
            cur.execute(
                """
                SELECT d.id, d.filename, COUNT(c.id) AS chunk_count
                FROM documents d
                LEFT JOIN chunks c ON c.document_id = d.id
                WHERE d.session_id = %s
                GROUP BY d.id, d.filename
                ORDER BY d.id;
                """,
                (session_id,),
            )
            rows = cur.fetchall()

    return [
        {"id": doc_id, "filename": filename, "chunk_count": chunk_count}
        for (doc_id, filename, chunk_count) in rows
    ]
