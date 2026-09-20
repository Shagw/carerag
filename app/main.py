# ============================================================================
# main.py — the FastAPI web app. This defines the API endpoints (URLs).
#
# Right now it has:
#   GET  /         -> a simple health check ("is the server alive?")
#   POST /upload   -> accept one or more PDFs, extract -> chunk -> embed -> store
#
# We'll add POST /ask (and others) in a later task.
#
# HOW YOU RUN THE SERVER (later):
#     uvicorn app.main:app --reload
#   then open http://localhost:8000/docs to try the endpoints in the browser.
# ============================================================================

from typing import List
import uuid  # to generate a random session id when the client doesn't send one

# FastAPI is the app; UploadFile/File handle uploaded files;
# HTTPException lets us return clean error responses.
from fastapi import FastAPI, UploadFile, File, Form, HTTPException

# Our own pipeline pieces (each does one job).
from app.pdf_utils import extract_pages          # PDF bytes -> [(page, text)]
from app.chunking import chunk_pages             # [(page, text)] -> [(page, chunk)]
from app.vector_store import save_chunks, list_documents  # store + list documents
from app.rag import answer_question              # the full RAG pipeline
from app.conversations import save_conversation, get_recent_history, get_full_history  # chat memory
from app.chats import create_chat, list_chats, rename_chat  # multi-chat workspace
from app.owners import create_owner, get_owner  # workspace owners
from app.models import (
    UploadResponse,
    UploadedDocument,
    AskRequest,
    AskResponse,
    Citation,
    DocumentInfo,
    CreateChatRequest,
    RenameChatRequest,
    ChatInfo,
    CreateOwnerRequest,
    OwnerInfo,
)


# Create the FastAPI application object.
app = FastAPI(title="CareRAG - Healthcare Policy Assistant")


# The biggest file we accept: 10 MB. (10 * 1024 * 1024 bytes.)
MAX_FILE_SIZE = 10 * 1024 * 1024


@app.get("/")
def health_check():
    """
    A simple endpoint to confirm the server is running.
    Visiting http://localhost:8000/ returns this small JSON.
    """
    return {"status": "ok", "service": "CareRAG"}


@app.post("/upload", response_model=UploadResponse)
async def upload_documents(
    files: List[UploadFile] = File(...),
    session_id: str = Form(...),
):
    """
    Upload one or more PDF files for a given session. For each file we:
        1. read its bytes,
        2. check size (<= 10 MB),
        3. extract text with page numbers (pdf_utils),
        4. split into chunks (chunking),
        5. embed + store in the database (vector_store), tagged with session_id.

    Returns a summary of what was stored.

    `session_id` comes as a form field (sent alongside the files). It ties each
    document to the uploader's session so they only see their own documents.
    `async def` + `await file.read()` lets the server handle uploads efficiently.
    """
    stored_documents: List[UploadedDocument] = []
    total_chunks = 0

    # Process each uploaded file one by one.
    for file in files:
        # --- Read the file's raw bytes into memory. ---
        contents = await file.read()

        # --- Size check: reject files bigger than 10 MB. ---
        if len(contents) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"'{file.filename}' is larger than 10 MB. Please upload a smaller PDF.",
            )

        # --- Run the ingestion pipeline for this file. ---
        # pdf_utils raises ValueError for a bad or scanned (no-text) PDF; we
        # catch it and return a friendly 400 error instead of crashing.
        try:
            pages = extract_pages(contents)         # [(page_number, text), ...]
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"'{file.filename}': {str(e)}")

        chunks = chunk_pages(pages)                 # [(page_number, chunk), ...]

        # Save this document + its chunks (tagged with session_id); get the id.
        document_id = save_chunks(file.filename, chunks, session_id)

        # Record what we stored for the response summary.
        stored_documents.append(
            UploadedDocument(
                document_id=document_id,
                filename=file.filename,
                chunks_stored=len(chunks),
            )
        )
        total_chunks += len(chunks)

    # Build the final friendly response.
    return UploadResponse(
        message=f"Stored {len(stored_documents)} document(s) with {total_chunks} chunk(s).",
        documents=stored_documents,
        total_chunks=total_chunks,
    )


@app.post("/ask", response_model=AskResponse)
def ask_question(request: AskRequest):
    """
    Ask a question about the uploaded documents.

    STEPS:
        1. Figure out the session id (create one if the client didn't send it).
        2. Load recent chat history for that session (for follow-up context).
        3. Run the RAG pipeline (retrieve -> guard -> answer -> citations).
        4. Save this Q&A turn to the conversations table (history/memory).
        5. Return the answer + citations + session id.
    """
    # 1) Use the client's session id, or make a new random one for a fresh chat.
    session_id = request.session_id or str(uuid.uuid4())

    # 2) Load the last few (question, answer) turns so follow-ups have context.
    history = get_recent_history(session_id, limit=5)

    # 3) Run the full RAG pipeline (searching only THIS session's documents).
    result = answer_question(request.question, session_id=session_id, history=history)

    # 4) Save this turn so it becomes part of the history next time.
    save_conversation(
        session_id=session_id,
        question=request.question,
        answer=result["answer"],
        sources=result["sources"],
    )

    # 5) Build and return the response. We convert each source dict into a
    #    Citation model so the API docs show a clear shape.
    citations = [Citation(**source) for source in result["sources"]]
    return AskResponse(
        answer=result["answer"],
        sources=citations,
        session_id=session_id,
    )


@app.get("/documents", response_model=List[DocumentInfo])
def get_documents(session_id: str):
    """
    List the documents uploaded by THIS session (per-session isolation).
    `session_id` is a query parameter, e.g. /documents?session_id=abc123
    The UI uses this to show the user their own knowledge base.
    """
    docs = list_documents(session_id)
    return [DocumentInfo(**doc) for doc in docs]


@app.get("/history")
def get_history(session_id: str):
    """
    Return this session's full chat history (with citations), oldest first.
    The UI calls this on page load so a refresh restores the conversation.
    e.g. /history?session_id=abc123
    """
    return get_full_history(session_id)


# ----------------------------------------------------------------------------
# Chat management endpoints (multi-chat workspace).
# A chat's id doubles as the session_id used by /upload, /ask, /documents,
# /history — so each chat has its own isolated documents, history, and search.
# ----------------------------------------------------------------------------

@app.post("/chats", response_model=ChatInfo)
def create_new_chat(request: CreateChatRequest):
    """Create a new named chat under an owner and return it (with its new id)."""
    chat_id = create_chat(request.name, request.owner_id)
    return ChatInfo(id=chat_id, name=request.name)


@app.get("/chats", response_model=List[ChatInfo])
def get_chats(owner_id: str):
    """List THIS owner's chats (newest first). e.g. /chats?owner_id=abc123"""
    return [ChatInfo(**chat) for chat in list_chats(owner_id)]


@app.patch("/chats/{chat_id}", response_model=ChatInfo)
def rename_existing_chat(chat_id: str, request: RenameChatRequest):
    """Rename an existing chat."""
    rename_chat(chat_id, request.name)
    return ChatInfo(id=chat_id, name=request.name)


# ----------------------------------------------------------------------------
# Owner (workspace) endpoints. An owner id is the key kept in the UI URL.
# ----------------------------------------------------------------------------

@app.post("/owners", response_model=OwnerInfo)
def create_new_owner(request: CreateOwnerRequest):
    """Create a new owner (workspace) with a display name; returns its new id."""
    owner_id = create_owner(request.name)
    return OwnerInfo(id=owner_id, name=request.name)


@app.get("/owners/{owner_id}", response_model=OwnerInfo)
def get_existing_owner(owner_id: str):
    """Look up an owner by id (to validate it and show the name)."""
    owner = get_owner(owner_id)
    if owner is None:
        raise HTTPException(status_code=404, detail="Owner not found.")
    return OwnerInfo(**owner)
