# ============================================================================
# streamlit_app.py — the CareRAG chat web page (pure Python UI).
#
# What the user can do here:
#   - Upload PDF documents (sidebar)
#   - See the list of THEIR uploaded documents (sidebar)
#   - Ask questions in a chat box and get answers with clickable citations
#
# This UI does NOT do any AI itself. It just calls our FastAPI backend over
# HTTP (using the `requests` library):
#   POST /upload      -> send PDFs
#   POST /ask         -> send a question, get answer + citations
#   GET  /documents   -> list this session's documents
#
# HOW TO RUN (needs the backend running too):
#   Terminal 1:  uvicorn app.main:app --reload
#   Terminal 2:  streamlit run ui/streamlit_app.py
# ============================================================================

import uuid
import requests
import streamlit as st

# Where the FastAPI backend lives. For local dev this is the default.
# (We read it directly here so the UI has no other dependencies.)
API_BASE_URL = "http://localhost:8000"


# ----------------------------------------------------------------------------
# Page setup
# ----------------------------------------------------------------------------
st.set_page_config(page_title="CareRAG", page_icon="🏥", layout="centered")
st.title("🏥 CareRAG — Healthcare Policy Assistant")
st.caption("Upload your policy / bill / discharge documents and ask questions. "
           "Every answer shows the exact source page.")


# ----------------------------------------------------------------------------
# Session state: values that must survive Streamlit's re-runs.
# Streamlit re-runs this whole script on every click, so we keep persistent
# things (our session id and the chat messages) in st.session_state.
# ----------------------------------------------------------------------------

# A unique id for THIS browser session. Created once, then reused. It ties the
# user to their own uploaded documents (per-session isolation).
#
# We persist the session id in the URL (e.g. ...?session=abc123). This way a
# page REFRESH keeps the SAME session, so documents you upload stay visible.
# Without this, Streamlit would make a new id on every refresh and you'd lose
# access to what you just uploaded.
if "session_id" not in st.session_state:
    # If the URL already has a session id, reuse it; otherwise make a new one.
    existing = st.query_params.get("session")
    if existing:
        st.session_state.session_id = existing
    else:
        new_id = str(uuid.uuid4())
        st.session_state.session_id = new_id
        # Write it into the URL so a refresh keeps this same session.
        st.query_params["session"] = new_id

# The chat history we DISPLAY on screen: a list of {"role", "content", "sources"}.
# On first load we fetch any saved history for this session from the backend,
# so refreshing the page (same session URL) restores the conversation.
if "messages" not in st.session_state:
    st.session_state.messages = []
    try:
        resp = requests.get(
            f"{API_BASE_URL}/history",
            params={"session_id": st.session_state.session_id},
        )
        if resp.status_code == 200:
            for turn in resp.json():
                # Each saved turn becomes a user bubble then an assistant bubble.
                st.session_state.messages.append(
                    {"role": "user", "content": turn["question"], "sources": []}
                )
                st.session_state.messages.append(
                    {"role": "assistant", "content": turn["answer"], "sources": turn.get("sources", [])}
                )
    except requests.exceptions.RequestException:
        # Backend not up yet — just start with an empty chat.
        pass


# ----------------------------------------------------------------------------
# Helper functions that call the backend.
# ----------------------------------------------------------------------------

def upload_files(uploaded_files):
    """Send the chosen PDF files to POST /upload for this session."""
    # Build the multipart "files" payload requests expects:
    # a list of ("files", (filename, bytes, content_type)) tuples.
    files_payload = [
        ("files", (f.name, f.getvalue(), "application/pdf"))
        for f in uploaded_files
    ]
    # The session id travels as a normal form field alongside the files.
    data = {"session_id": st.session_state.session_id}

    response = requests.post(f"{API_BASE_URL}/upload", files=files_payload, data=data)
    return response


def fetch_documents():
    """Get the list of documents this session has uploaded (GET /documents)."""
    try:
        response = requests.get(
            f"{API_BASE_URL}/documents",
            params={"session_id": st.session_state.session_id},
        )
        if response.status_code == 200:
            return response.json()
    except requests.exceptions.RequestException:
        # Backend not running or unreachable — just show nothing.
        pass
    return []


def ask_question(question):
    """Send a question to POST /ask and return the parsed JSON answer."""
    response = requests.post(
        f"{API_BASE_URL}/ask",
        json={"question": question, "session_id": st.session_state.session_id},
    )
    response.raise_for_status()  # raise if the server returned an error
    return response.json()


# ----------------------------------------------------------------------------
# Sidebar: upload documents + show this session's document list.
# ----------------------------------------------------------------------------
with st.sidebar:
    st.header("📁 Your documents")

    uploaded = st.file_uploader(
        "Upload PDF(s)",
        type=["pdf"],
        accept_multiple_files=True,
    )

    # The upload only happens when the user clicks the button (not on every
    # re-run), so we don't re-upload the same files repeatedly.
    if st.button("Upload", disabled=not uploaded):
        with st.spinner("Reading, chunking, and embedding your documents..."):
            resp = upload_files(uploaded)
        if resp.status_code == 200:
            st.success(resp.json()["message"])
        else:
            # Show the backend's friendly error (e.g. scanned PDF, too big).
            try:
                st.error(resp.json().get("detail", "Upload failed."))
            except Exception:
                st.error("Upload failed.")

    st.divider()

    # Show the documents currently stored for this session.
    docs = fetch_documents()
    if docs:
        st.write("In your knowledge base:")
        for d in docs:
            st.write(f"• {d['filename']}  ({d['chunk_count']} chunks)")
    else:
        st.info("No documents yet. Upload a PDF to begin.")

    st.divider()
    st.caption("Your documents are private to this browser session.")


# ----------------------------------------------------------------------------
# Main area: the chat.
# ----------------------------------------------------------------------------

# 1) Re-draw all past messages every run (so the conversation stays visible).
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])

        # For assistant messages, show the citations in collapsible boxes.
        for source in message.get("sources", []):
            with st.expander(f"📄 {source['filename']} — page {source['page_number']}"):
                st.write(source["snippet"])

# 2) The input box at the bottom. Returns the typed text when the user hits enter.
question = st.chat_input("Ask a question about your documents...")

if question:
    # Show the user's message immediately.
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.write(question)

    # Call the backend and show the assistant's answer.
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                result = ask_question(question)
                answer = result["answer"]
                sources = result["sources"]
            except requests.exceptions.RequestException:
                answer = "Could not reach the server. Is the backend running?"
                sources = []

        st.write(answer)

        # Show each citation in its own collapsible box (filename, page, snippet).
        for source in sources:
            with st.expander(f"📄 {source['filename']} — page {source['page_number']}"):
                st.write(source["snippet"])

    # Save the assistant message (with sources) so it redraws on later runs.
    st.session_state.messages.append(
        {"role": "assistant", "content": answer, "sources": sources}
    )
