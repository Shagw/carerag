# ============================================================================
# chats.py — manage the list of named chats (the multi-chat workspace).
#
# A "chat" is just a named container. Its `id` (a UUID) is the SAME value we
# use as `session_id` for documents and conversations — so each chat already
# gets its own isolated documents, history, and search for free.
#
# Each chat belongs to an OWNER (a workspace). We filter chats by owner_id so
# each person only sees their own chats.
#
# Functions:
#   create_chat(name, owner_id) -> new chat id
#   list_chats(owner_id)        -> that owner's chats, newest first
#   rename_chat(id, name)
# ============================================================================

import uuid
from typing import List, Dict, Any

from app.database import get_connection


def create_chat(name: str, owner_id: str) -> str:
    """
    Create a new chat (owned by owner_id) and return its new id (a UUID string).
    """
    chat_id = str(uuid.uuid4())
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO chats (id, owner_id, name) VALUES (%s, %s, %s);",
                (chat_id, owner_id, name),
            )
    return chat_id


def list_chats(owner_id: str) -> List[Dict[str, Any]]:
    """
    Return THIS owner's chats, newest first.
    Output: [{ "id": "uuid", "name": "Health Policy" }, ...]
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name FROM chats WHERE owner_id = %s ORDER BY created_at DESC;",
                (owner_id,),
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
