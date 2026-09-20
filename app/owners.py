# ============================================================================
# owners.py — a lightweight "owner" (workspace) for the multi-chat feature.
#
# An owner = one browser/workspace. Its `id` is a random UUID that lives in the
# page URL (?owner=...) and is the REAL key that isolates a person's chats.
# The `name` is only a friendly label (not unique, not a password).
#
# Functions:
#   create_owner(name) -> new owner id (a UUID string)
#   get_owner(owner_id) -> {"id", "name"} or None
# ============================================================================

import uuid
from typing import Optional, Dict, Any

from app.database import get_connection


def create_owner(name: str) -> str:
    """
    Create a new owner with the given display name and return its new id.

    The id is a random UUID (e.g. 'a3f8c2e1-9b4d-...'), NOT a guessable number,
    because it doubles as the access key kept in the URL.
    """
    owner_id = str(uuid.uuid4())
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO owners (id, name) VALUES (%s, %s);",
                (owner_id, name),
            )
    return owner_id


def get_owner(owner_id: str) -> Optional[Dict[str, Any]]:
    """
    Look up an owner by id. Returns {"id", "name"} or None if it doesn't exist.
    Used to (a) validate an owner id from the URL and (b) show the name.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name FROM owners WHERE id = %s;", (owner_id,))
            row = cur.fetchone()
    if row is None:
        return None
    return {"id": row[0], "name": row[1]}
