# ============================================================================
# models.py — the "shapes" of data our API sends and receives (Pydantic models).
#
# FastAPI uses these classes to:
#   1. validate data automatically, and
#   2. build the interactive API docs at http://localhost:8000/docs
#
# A Pydantic model is just a class listing fields and their types.
# We start with only what the UPLOAD endpoint needs; we'll add "ask" models
# later when we build that endpoint.
# ============================================================================

from typing import List

# BaseModel is the parent class that makes a normal class into a Pydantic model.
from pydantic import BaseModel


class UploadedDocument(BaseModel):
    """
    Describes ONE document that was successfully uploaded and stored.
    (One of these per file in a multi-file upload.)
    """
    document_id: int      # the id we got back from the database
    filename: str         # the original file name
    chunks_stored: int    # how many chunks we extracted and saved


class UploadResponse(BaseModel):
    """
    The overall reply the /upload endpoint sends back after processing files.
    """
    message: str                          # a friendly summary line
    documents: List[UploadedDocument]     # details for each stored document
    total_chunks: int                     # total chunks stored across all files


# ----------------------------------------------------------------------------
# Models for the /ask endpoint (asking a question, getting an answer).
# ----------------------------------------------------------------------------

class AskRequest(BaseModel):
    """
    What the client SENDS when asking a question.
    """
    question: str                         # the user's question
    # Optional id that groups messages of one chat together (for follow-up
    # memory). If the client doesn't send one, the API creates a new one.
    session_id: str = None


class Citation(BaseModel):
    """
    One source reference behind an answer: which document, which page, and a
    short quoted snippet (this is our "prove it's not made up" feature).
    """
    filename: str
    page_number: int
    snippet: str


class AskResponse(BaseModel):
    """
    What the /ask endpoint SENDS BACK.
    """
    answer: str                           # the generated answer (or "I don't know")
    sources: List[Citation]               # the citations behind the answer
    session_id: str                       # echo back the session id (for follow-ups)


# ----------------------------------------------------------------------------
# Model for the /documents endpoint (listing what's in the knowledge base).
# ----------------------------------------------------------------------------

class DocumentInfo(BaseModel):
    """
    Summary of one uploaded document, for the UI's document list.
    """
    id: int
    filename: str
    chunk_count: int


# ----------------------------------------------------------------------------
# Models for the /chats endpoints (multi-chat workspace).
# ----------------------------------------------------------------------------

class CreateChatRequest(BaseModel):
    """Client sends this to create a new chat."""
    name: str = "New chat"          # default name if none provided


class RenameChatRequest(BaseModel):
    """Client sends this to rename an existing chat."""
    name: str


class ChatInfo(BaseModel):
    """One chat in the sidebar list."""
    id: str
    name: str
