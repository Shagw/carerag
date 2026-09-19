# ============================================================================
# chats.py — manage the list of named chats (the multi-chat workspace).
#
# A "chat" is just a named container. Its `id` (a UUID) is the SAME value we
# use as `session_id` for documents and conversations — so each chat already
# gets its own isolated documents, history, and search for free.
#
# Functions:
#   create_chat(name) -> new chat id
#   list_chats()      -> all chats, newest first
#   rename_chat(id, name)
# ============================================================================

import uuid
from typing import List, Dict, Any

from app.database import get_connection


def create_chat(name: str) -> str:
    """
    Create a new chat with the given name and return its new id (a UUID string).
    """
    chat_id = str(uuid.uuid4())
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO chats (id, name) VALUES (%s, %s);",
                (chat_id, name),
            )
        conn.commit()
    return chat_id


def list_chats() -> List[Dict[str, Any]]:
    """
    Return all chats, newest first.
    Output: [{ "id": "uuid", "name": "Health Policy" }, ...]
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name FROM chats ORDER BY created_at DESC;"
            )
            rows = cur.fetchall()
    return [{"id": row[0], "name": row[1]} for row in rows]


def rename_chat(chat_id: str, new_name: str) -> None:
    """
    Change the display name of an existing chat.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE chats SET name = %s WHERE id = %s;",
                (new_name, chat_id),
            )
        conn.commit()
