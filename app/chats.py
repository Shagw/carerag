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
#   list_chats(owner_id)        -> that owner's ACTIVE chats, newest first
#   rename_chat(id, name)
#   delete_chat(id)             -> SOFT delete (hide from list, keep the data)
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
    Return THIS owner's ACTIVE chats, newest first.
    Soft-deleted chats (deleted_at IS NOT NULL) are excluded.
    Output: [{ "id": "uuid", "name": "Health Policy" }, ...]
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name FROM chats
                WHERE owner_id = %s AND deleted_at IS NULL
                ORDER BY created_at DESC;
                """,
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


def delete_chat(chat_id: str) -> None:
    """
    SOFT-delete a chat: mark it deleted (set deleted_at = now) so it disappears
    from the user's list, but keep the row AND its documents/history in the
    database. Nothing is physically removed — this is reversible by clearing
    deleted_at, and keeps data for audit/recovery.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE chats SET deleted_at = now() WHERE id = %s;",
                (chat_id,),
            )
