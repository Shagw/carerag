# ============================================================================
# conversations.py — save and load chat history (the "memory" feature).
#
# Two jobs:
#   1. save_conversation(...) .. store one Q&A turn (with its citations)
#   2. get_recent_history(...) . load the last few Q&A turns for a session
#
# History is grouped by `session_id` so follow-up questions in the SAME chat
# can be understood in context (e.g. "and what about for children?").
# ============================================================================

import json
from typing import List, Tuple, Dict, Any

from app.database import get_connection


def save_conversation(
    session_id: str,
    question: str,
    answer: str,
    sources: List[Dict[str, Any]],
) -> None:
    """
    Store one question/answer turn in the `conversations` table.

    `sources` (the citation list) is saved as JSONB so we keep the full detail
    (filename, page, snippet) and can show it again later if needed.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO conversations (session_id, question, answer, sources)
                VALUES (%s, %s, %s, %s);
                """,
                # json.dumps turns our Python list of dicts into a JSON string,
                # which Postgres stores in the JSONB `sources` column.
                (session_id, question, answer, json.dumps(sources)),
            )
        conn.commit()


def get_recent_history(session_id: str, limit: int = 5) -> List[Tuple[str, str]]:
    """
    Return the last `limit` (question, answer) pairs for a session, OLDEST first.

    Oldest-first ordering matters: when we feed history into the prompt, the
    conversation should read top-to-bottom in the order it happened.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Get the most recent rows first (DESC + LIMIT), then we reverse them
            # to oldest-first below.
            cur.execute(
                """
                SELECT question, answer
                FROM conversations
                WHERE session_id = %s
                ORDER BY created_at DESC
                LIMIT %s;
                """,
                (session_id, limit),
            )
            rows = cur.fetchall()

    # rows are newest-first; reverse to oldest-first for natural reading order.
    rows.reverse()

    # Turn each row tuple into a clean (question, answer) pair.
    return [(question, answer) for (question, answer) in rows]


def get_full_history(session_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Return the full chat history for a session, OLDEST first, INCLUDING sources.

    Used by the UI to redraw the whole conversation (with citations) after a
    page refresh. Each item: {"question", "answer", "sources": [...]}.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT question, answer, sources
                FROM conversations
                WHERE session_id = %s
                ORDER BY created_at ASC
                LIMIT %s;
                """,
                (session_id, limit),
            )
            rows = cur.fetchall()

    history = []
    for question, answer, sources in rows:
        # `sources` comes back from JSONB already as a Python list (psycopg
        # decodes JSONB automatically), or None if it was empty.
        history.append(
            {"question": question, "answer": answer, "sources": sources or []}
        )
    return history
