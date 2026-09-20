# ============================================================================
# streamlit_direct.py — CareRAG MULTI-CHAT web UI in "direct mode".
#
# "Direct mode": this UI calls the backend functions IN-PROCESS (no HTTP, no
# separate FastAPI server), so it deploys as ONE process on free hosts like
# Streamlit Community Cloud.
#
# Multi-chat workspace:
#   - Sidebar lists your chats. Click one to switch. "New chat" makes more.
#   - Each chat has its OWN documents, history, and search (isolated). A chat's
#     id doubles as the session_id used by the backend functions.
#   - You upload PDFs INSIDE the chat area (each chat = its own knowledge base).
#   - Every answer shows clickable citations (document + page + snippet).
#
# HOW TO RUN:
#   streamlit run ui/streamlit_direct.py
# ============================================================================

import sys
import os
import uuid

# Make sure Python can find the `app` package (this file lives in ui/).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st

# set_page_config MUST be the very first Streamlit command — before anything
# else that touches Streamlit (including reading st.secrets below).
st.set_page_config(page_title="CareRAG", page_icon="🏥", layout="centered")

# ---------------------------------------------------------------------------
# Bridge Streamlit Cloud secrets -> environment variables BEFORE importing app.
# (config.py reads settings from the environment at import time; on Streamlit
# Cloud there is no .env file, only st.secrets.)
#
# We only touch st.secrets if a secrets file actually exists — otherwise
# Streamlit logs a harmless "No secrets found" message locally. Locally we use
# the .env file instead, so this block simply does nothing.
# ---------------------------------------------------------------------------
try:
    # Only read st.secrets if a secrets.toml actually exists (checked with plain
    # Python so we never trigger Streamlit's "No secrets found" message locally).
    _secrets_paths = [
        os.path.expanduser("~/.streamlit/secrets.toml"),
        os.path.join(os.getcwd(), ".streamlit", "secrets.toml"),
    ]
    if any(os.path.exists(p) for p in _secrets_paths):
        for _key, _value in st.secrets.items():
            os.environ.setdefault(_key, str(_value))
except Exception:
    pass

# Import the backend logic DIRECTLY (no HTTP). Must come AFTER the bridge above.
from app.pdf_utils import extract_pages
from app.chunking import chunk_pages
from app.vector_store import save_chunks, list_documents
from app.rag import answer_question
from app.conversations import save_conversation, get_recent_history, get_full_history
from app.chats import create_chat, list_chats, rename_chat
from app.owners import create_owner, get_owner


# ---------------------------------------------------------------------------
# Small helpers.
# ---------------------------------------------------------------------------

def load_history_into_state(chat_id: str):
    """Fill st.session_state.messages from the DB for the given chat."""
    st.session_state.messages = []
    try:
        for turn in get_full_history(chat_id):
            st.session_state.messages.append(
                {"role": "user", "content": turn["question"], "sources": []}
            )
            st.session_state.messages.append(
                {"role": "assistant", "content": turn["answer"], "sources": turn.get("sources", [])}
            )
    except Exception:
        pass


def ingest_file(uploaded_file, chat_id: str) -> str:
    """Extract -> chunk -> embed -> store one uploaded PDF for this chat."""
    data = uploaded_file.getvalue()
    if len(data) > 10 * 1024 * 1024:
        return f"'{uploaded_file.name}' is larger than 10 MB."
    try:
        pages = extract_pages(data)
    except ValueError as e:
        return f"'{uploaded_file.name}': {e}"
    chunks = chunk_pages(pages)
    save_chunks(uploaded_file.name, chunks, chat_id)
    return f"Stored '{uploaded_file.name}' ({len(chunks)} chunks)."


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# OWNER (workspace) gate.
# A visitor needs an owner id (kept in the URL as ?owner=...). If they don't
# have a valid one yet, we ask their name and create a fresh owner. The owner
# id — NOT the name — is the key that isolates their chats.
# ---------------------------------------------------------------------------
url_owner = st.query_params.get("owner")
owner = get_owner(url_owner) if url_owner else None

if owner is None:
    # New visitor (or unknown owner id): show a friendly name prompt and stop.
    st.title("🏥 CareRAG")
    st.subheader("Welcome! What should we call you?")
    st.caption("This creates your private workspace. Bookmark the URL that "
               "appears afterward to come back to your chats.")
    name = st.text_input("Your name")
    if st.button("Start", disabled=not name.strip()):
        new_owner_id = create_owner(name.strip())
        st.query_params["owner"] = new_owner_id
        st.rerun()
    st.stop()   # don't render the rest until we have an owner

owner_id = owner["id"]

# Decide the active chat. We keep the current chat id in the URL (?chat=...)
# so a refresh stays on the same chat.
# ---------------------------------------------------------------------------
chats = list_chats(owner_id)

# If this owner has NO chats yet, create the first one automatically.
if not chats:
    create_chat("New chat", owner_id)
    chats = list_chats(owner_id)

valid_ids = [c["id"] for c in chats]
names_by_id = {c["id"]: c["name"] for c in chats}

# Which chat should be pre-selected? Prefer the one in the URL, else the first.
url_chat = st.query_params.get("chat")
default_id = url_chat if url_chat in valid_ids else valid_ids[0]

# ---------------------------------------------------------------------------
# Sidebar: chat list (the radio is the SINGLE SOURCE OF TRUTH for the active
# chat) + new chat + rename. We render this FIRST so the rest of the page uses
# the freshly-selected chat in the SAME run — no one-rerun lag / stale lists.
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("💬 Your chats")
    st.caption(f"Workspace: **{owner['name']}**")

    if st.button("➕ New chat", use_container_width=True):
        new_id = create_chat("New chat", owner_id)
        st.query_params["chat"] = new_id
        st.rerun()

    st.divider()

    current_chat_id = st.radio(
        "Switch chat",
        options=valid_ids,
        index=valid_ids.index(default_id),
        format_func=lambda cid: names_by_id.get(cid, "Chat"),
    )
    # Keep the URL in sync with the radio (so a refresh stays on this chat).
    if st.query_params.get("chat") != current_chat_id:
        st.query_params["chat"] = current_chat_id

    st.divider()

    st.caption("Rename this chat")
    new_name = st.text_input("New name", value=names_by_id.get(current_chat_id, ""))
    if st.button("Rename", use_container_width=True):
        if new_name.strip():
            rename_chat(current_chat_id, new_name.strip())
            st.rerun()

# When the active chat CHANGES, reload that chat's history into the screen.
# (This runs AFTER the radio, so current_chat_id is already the new chat.)
if st.session_state.get("active_chat_id") != current_chat_id:
    st.session_state.active_chat_id = current_chat_id
    load_history_into_state(current_chat_id)


# ---------------------------------------------------------------------------
# Main area: title, in-chat upload + this chat's documents, then the chat.
# ---------------------------------------------------------------------------
st.title("🏥 CareRAG")
st.caption(f"Chat: **{names_by_id.get(current_chat_id, 'New chat')}** — "
           "upload documents and ask questions. Answers cite their source page.")

with st.expander("📎 Add documents to this chat", expanded=not st.session_state.messages):
    uploaded = st.file_uploader(
        "Upload PDF(s) for this chat", type=["pdf"], accept_multiple_files=True,
        key=f"uploader_{current_chat_id}",   # unique per chat → resets on switch
    )
    if st.button("Upload to this chat", disabled=not uploaded, key=f"uploadbtn_{current_chat_id}"):
        with st.spinner("Reading, chunking, and embedding..."):
            for f in uploaded:
                msg = ingest_file(f, current_chat_id)
                (st.success if msg.startswith("Stored") else st.error)(msg)

    try:
        docs = list_documents(current_chat_id)
    except Exception:
        docs = []
    if docs:
        st.write("In this chat:")
        for d in docs:
            st.write(f"• {d['filename']}  ({d['chunk_count']} chunks)")
    else:
        st.info("No documents in this chat yet.")

st.divider()

# Redraw the current chat's messages.
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])
        for source in message.get("sources", []):
            with st.expander(f"📄 {source['filename']} — page {source['page_number']}"):
                st.write(source["snippet"])

question = st.chat_input("Ask a question about this chat's documents...")

if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.write(question)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                history = get_recent_history(current_chat_id, limit=5)
                result = answer_question(question, session_id=current_chat_id, history=history)
                answer = result["answer"]
                sources = result["sources"]
                save_conversation(current_chat_id, question, answer, sources)
            except Exception as e:
                answer = f"Something went wrong: {e}"
                sources = []

        st.write(answer)
        for source in sources:
            with st.expander(f"📄 {source['filename']} — page {source['page_number']}"):
                st.write(source["snippet"])

    st.session_state.messages.append(
        {"role": "assistant", "content": answer, "sources": sources}
    )
