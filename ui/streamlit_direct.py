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
from app.chats import create_chat, list_chats, rename_chat, delete_chat
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
    """Read a PDF and get it ready for questions. Returns a friendly message."""
    data = uploaded_file.getvalue()
    if len(data) > 10 * 1024 * 1024:
        return f"'{uploaded_file.name}' is too large (over 10 MB). Please try a smaller file."
    try:
        pages = extract_pages(data)
    except ValueError as e:
        return f"Couldn't read '{uploaded_file.name}': {e}"
    chunks = chunk_pages(pages)
    save_chunks(uploaded_file.name, chunks, chat_id)
    return f"Added '{uploaded_file.name}'. You can ask questions about it now."


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
    st.title("🏥 CareRAG — Your Health Document Assistant")
    st.subheader("Welcome! What's your name?")
    st.caption("We'll set up a private space just for you. "
               "Tip: save this page's web address (URL) so you can come back to your documents later.")
    name = st.text_input("Your name")
    if st.button("Get started", disabled=not name.strip()):
        new_owner_id = create_owner(name.strip())
        st.query_params["owner"] = new_owner_id
        st.rerun()
    st.stop()   # don't render the rest until we have an owner

owner_id = owner["id"]

# Decide the active chat. We keep the current chat id in the URL (?chat=...)
# so a refresh stays on the same chat.
# ---------------------------------------------------------------------------

# If we just deleted a conversation on the previous run, reset the selection
# HERE (before the radio widget is created) so we don't point at the deleted
# chat. Doing it here — not inline in the button — avoids Streamlit errors from
# mutating a live widget's key.
if st.session_state.pop("_just_deleted", False):
    st.session_state.pop("chat_choice", None)   # safe now: radio not yet created
    if "chat" in st.query_params:
        del st.query_params["chat"]

chats = list_chats(owner_id)

# If this owner has NO chats yet (including right after deleting the last one),
# create a fresh one automatically so there's always somewhere to work.
if not chats:
    create_chat("New conversation", owner_id)
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
    st.header("💬 Your conversations")
    st.caption(f"Signed in as **{owner['name']}**")

    if st.button("➕ Start a new conversation", use_container_width=True):
        new_id = create_chat("New conversation", owner_id)
        st.session_state.chat_choice = new_id   # select the new chat in the radio
        st.query_params["chat"] = new_id
        st.rerun()

    st.divider()

    # Seed the radio's selection from the URL ONCE (or when the stored choice is
    # no longer valid, e.g. after creating a new chat). After that, the radio's
    # own state (key='chat_choice') is the source of truth — we do NOT pass
    # index=, which previously forced the selection back to the URL each run and
    # caused the "need to click twice" lag.
    if st.session_state.get("chat_choice") not in valid_ids:
        st.session_state.chat_choice = default_id

    current_chat_id = st.radio(
        "Choose a conversation",
        options=valid_ids,
        format_func=lambda cid: names_by_id.get(cid, "Conversation"),
        key="chat_choice",
    )
    # Keep the URL in sync with the radio (so a refresh stays on this chat).
    if st.query_params.get("chat") != current_chat_id:
        st.query_params["chat"] = current_chat_id

    st.divider()

    st.caption("Rename this conversation")
    # Chat-scoped key so the box shows the CURRENT chat's name and resets when
    # you switch chats. We seed the box's value once per chat via session_state
    # (setting value= every run fights Streamlit's own widget state and made a
    # second rename not register).
    rename_key = f"rename_{current_chat_id}"
    if rename_key not in st.session_state:
        st.session_state[rename_key] = names_by_id.get(current_chat_id, "")
    new_name = st.text_input("New name", key=rename_key)
    if st.button("Save name", use_container_width=True):
        if new_name.strip() and new_name.strip() != names_by_id.get(current_chat_id, ""):
            rename_chat(current_chat_id, new_name.strip())
            st.rerun()

    st.divider()

    # Delete the current conversation (soft delete). A confirm checkbox avoids
    # accidental clicks. We do the actual delete here, then set a flag and
    # rerun — the flag is handled at the TOP of the next run (before the radio
    # widget is created), which is the safe place to reset the selection.
    st.caption("Delete this conversation")
    confirm = st.checkbox("Yes, remove it from my list", key=f"confirmdel_{current_chat_id}")
    if st.button("🗑️ Delete conversation", use_container_width=True):
        if confirm:
            delete_chat(current_chat_id)
            st.session_state["_just_deleted"] = True
            st.rerun()
        else:
            st.warning("Please tick the box above to confirm deletion.")

# When the active chat CHANGES, reload that chat's history into the screen.
# (This runs AFTER the radio, so current_chat_id is already the new chat.)
if st.session_state.get("active_chat_id") != current_chat_id:
    st.session_state.active_chat_id = current_chat_id
    load_history_into_state(current_chat_id)


# ---------------------------------------------------------------------------
# Main area: title, in-chat upload + this chat's documents, then the chat.
# ---------------------------------------------------------------------------
st.title("🏥 CareRAG")
st.caption(f"Conversation: **{names_by_id.get(current_chat_id, 'New conversation')}** — "
           "add your health or insurance documents, then ask questions in plain English. "
           "Each answer shows which document and page it came from.")

with st.expander("📎 Add documents to this conversation", expanded=not st.session_state.messages):
    uploaded = st.file_uploader(
        "Choose PDF file(s) — e.g. a policy, bill, or discharge summary",
        type=["pdf"], accept_multiple_files=True,
        key=f"uploader_{current_chat_id}",   # unique per chat → resets on switch
    )
    if st.button("Add these documents", disabled=not uploaded, key=f"uploadbtn_{current_chat_id}"):
        with st.spinner("Reading your documents and getting them ready... this can take a moment."):
            for f in uploaded:
                msg = ingest_file(f, current_chat_id)
                (st.success if msg.startswith("Added") else st.error)(msg)

    try:
        docs = list_documents(current_chat_id)
    except Exception:
        docs = []
    if docs:
        st.write("Documents in this conversation:")
        for d in docs:
            st.write(f"• {d['filename']}")
    else:
        st.info("No documents added yet. Add a PDF above to get started.")

st.divider()

# Redraw the current chat's messages.
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])
        for source in message.get("sources", []):
            with st.expander(f"📄 Source: {source['filename']} — page {source['page_number']}"):
                st.write(source["snippet"])

question = st.chat_input("Type your question here...")

if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.write(question)

    with st.chat_message("assistant"):
        with st.spinner("Looking through your documents..."):
            try:
                history = get_recent_history(current_chat_id, limit=5)
                result = answer_question(question, session_id=current_chat_id, history=history)
                answer = result["answer"]
                sources = result["sources"]
                save_conversation(current_chat_id, question, answer, sources)
            except Exception:
                answer = ("Sorry, something went wrong while answering. "
                          "Please try again in a moment.")
                sources = []

        st.write(answer)
        for source in sources:
            with st.expander(f"📄 {source['filename']} — page {source['page_number']}"):
                st.write(source["snippet"])

    st.session_state.messages.append(
        {"role": "assistant", "content": answer, "sources": sources}
    )
