# ============================================================================
# streamlit_app.py — CareRAG multi-chat web UI (pure Python).
#
# Multi-chat workspace:
#   - Sidebar lists your chats. Click one to switch to it. "New chat" makes more.
#   - Each chat has its OWN documents, history, and search (isolated).
#   - You upload PDFs INSIDE the chat area (not a global sidebar).
#   - Every answer shows clickable citations (document + page + snippet).
#
# The UI talks to the FastAPI backend over HTTP. A chat's id is used as the
# `session_id` for upload/ask/documents/history — that's what isolates chats.
#
# HOW TO RUN (needs the backend running too):
#   Terminal 1:  uvicorn app.main:app --reload
#   Terminal 2:  streamlit run ui/streamlit_app.py
# ============================================================================

import requests
import streamlit as st

API_BASE_URL = "http://localhost:8000"


# ----------------------------------------------------------------------------
# Page setup
# ----------------------------------------------------------------------------
st.set_page_config(page_title="CareRAG", page_icon="🏥", layout="centered")


# ----------------------------------------------------------------------------
# Backend helper functions (each is one small HTTP call).
# ----------------------------------------------------------------------------

def api_list_chats():
    """GET /chats -> list of {id, name} (newest first)."""
    try:
        r = requests.get(f"{API_BASE_URL}/chats")
        if r.status_code == 200:
            return r.json()
    except requests.exceptions.RequestException:
        pass
    return []


def api_create_chat(name="New chat"):
    """POST /chats -> the new {id, name}."""
    r = requests.post(f"{API_BASE_URL}/chats", json={"name": name})
    r.raise_for_status()
    return r.json()


def api_rename_chat(chat_id, name):
    """PATCH /chats/{id} -> renamed {id, name}."""
    r = requests.patch(f"{API_BASE_URL}/chats/{chat_id}", json={"name": name})
    r.raise_for_status()
    return r.json()


def api_documents(chat_id):
    """GET /documents?session_id=chat_id -> this chat's documents."""
    try:
        r = requests.get(f"{API_BASE_URL}/documents", params={"session_id": chat_id})
        if r.status_code == 200:
            return r.json()
    except requests.exceptions.RequestException:
        pass
    return []


def api_history(chat_id):
    """GET /history?session_id=chat_id -> this chat's past turns (with sources)."""
    try:
        r = requests.get(f"{API_BASE_URL}/history", params={"session_id": chat_id})
        if r.status_code == 200:
            return r.json()
    except requests.exceptions.RequestException:
        pass
    return []


def api_upload(chat_id, uploaded_files):
    """POST /upload -> send PDFs for this chat (session_id = chat_id)."""
    files_payload = [
        ("files", (f.name, f.getvalue(), "application/pdf"))
        for f in uploaded_files
    ]
    return requests.post(
        f"{API_BASE_URL}/upload",
        files=files_payload,
        data={"session_id": chat_id},
    )


def api_ask(chat_id, question):
    """POST /ask -> answer + citations for this chat."""
    r = requests.post(
        f"{API_BASE_URL}/ask",
        json={"question": question, "session_id": chat_id},
    )
    r.raise_for_status()
    return r.json()


def load_history_into_state(chat_id):
    """Fill st.session_state.messages from the backend for the given chat."""
    st.session_state.messages = []
    for turn in api_history(chat_id):
        st.session_state.messages.append(
            {"role": "user", "content": turn["question"], "sources": []}
        )
        st.session_state.messages.append(
            {"role": "assistant", "content": turn["answer"], "sources": turn.get("sources", [])}
        )


# ----------------------------------------------------------------------------
# Decide which chat is active. We keep the current chat id in the URL
# (?chat=...) so a refresh stays on the same chat.
# ----------------------------------------------------------------------------

# Make sure the backend is reachable before doing anything else.
chats = api_list_chats()

# If there are NO chats yet, create the first one automatically.
if not chats:
    try:
        first = api_create_chat("New chat")
        chats = [first]
    except requests.exceptions.RequestException:
        st.error("Could not reach the backend. Is `uvicorn app.main:app` running?")
        st.stop()

# Which chat is selected? Prefer the one in the URL; else the newest.
current_chat_id = st.query_params.get("chat")
valid_ids = [c["id"] for c in chats]
if current_chat_id not in valid_ids:
    current_chat_id = chats[0]["id"]
    st.query_params["chat"] = current_chat_id

# When the selected chat CHANGES, reload that chat's history into the screen.
if st.session_state.get("active_chat_id") != current_chat_id:
    st.session_state.active_chat_id = current_chat_id
    load_history_into_state(current_chat_id)


# ----------------------------------------------------------------------------
# Sidebar: chat list + new chat + rename current chat.
# ----------------------------------------------------------------------------
with st.sidebar:
    st.header("💬 Your chats")

    # New chat button — creates a chat and switches to it.
    if st.button("➕ New chat", use_container_width=True):
        new_chat = api_create_chat("New chat")
        st.query_params["chat"] = new_chat["id"]
        st.rerun()  # reload so the new chat becomes active

    st.divider()

    # The list of chats as clickable options. We show names; selecting one
    # switches the active chat via the URL.
    names_by_id = {c["id"]: c["name"] for c in chats}
    selected = st.radio(
        "Switch chat",
        options=valid_ids,
        index=valid_ids.index(current_chat_id),
        format_func=lambda cid: names_by_id.get(cid, "Chat"),
    )
    if selected != current_chat_id:
        st.query_params["chat"] = selected
        st.rerun()

    st.divider()

    # Rename the CURRENT chat (option A: text box + button).
    st.caption("Rename this chat")
    new_name = st.text_input("New name", value=names_by_id.get(current_chat_id, ""))
    if st.button("Rename", use_container_width=True):
        if new_name.strip():
            api_rename_chat(current_chat_id, new_name.strip())
            st.rerun()


# ----------------------------------------------------------------------------
# Main area: title, in-chat upload, this chat's documents, then the chat.
# ----------------------------------------------------------------------------
st.title("🏥 CareRAG")
st.caption(f"Chat: **{names_by_id.get(current_chat_id, 'New chat')}** — "
           "upload documents and ask questions. Answers cite their source page.")

# In-chat upload (inside the chat area, not a global sidebar).
with st.expander("📎 Add documents to this chat", expanded=not st.session_state.messages):
    uploaded = st.file_uploader(
        "Upload PDF(s) for this chat",
        type=["pdf"],
        accept_multiple_files=True,
    )
    if st.button("Upload to this chat", disabled=not uploaded):
        with st.spinner("Reading, chunking, and embedding..."):
            resp = api_upload(current_chat_id, uploaded)
        if resp.status_code == 200:
            st.success(resp.json()["message"])
        else:
            try:
                st.error(resp.json().get("detail", "Upload failed."))
            except Exception:
                st.error("Upload failed.")

    # Show the documents that belong to THIS chat.
    docs = api_documents(current_chat_id)
    if docs:
        st.write("In this chat:")
        for d in docs:
            st.write(f"• {d['filename']}  ({d['chunk_count']} chunks)")
    else:
        st.info("No documents in this chat yet.")

st.divider()

# Redraw past messages of the current chat.
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])
        for source in message.get("sources", []):
            with st.expander(f"📄 {source['filename']} — page {source['page_number']}"):
                st.write(source["snippet"])

# The chat input box.
question = st.chat_input("Ask a question about this chat's documents...")

if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.write(question)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                result = api_ask(current_chat_id, question)
                answer = result["answer"]
                sources = result["sources"]
            except requests.exceptions.RequestException:
                answer = "Could not reach the server. Is the backend running?"
                sources = []

        st.write(answer)
        for source in sources:
            with st.expander(f"📄 {source['filename']} — page {source['page_number']}"):
                st.write(source["snippet"])

    st.session_state.messages.append(
        {"role": "assistant", "content": answer, "sources": sources}
    )
