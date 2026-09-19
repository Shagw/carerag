# ============================================================================
# streamlit_direct.py — CareRAG chat UI in "direct mode".
#
# DIFFERENCE FROM streamlit_app.py:
#   - streamlit_app.py talks to the FastAPI backend over HTTP (needs uvicorn
#     running separately). Good for local dev with the real API + /docs.
#   - THIS file calls the backend functions DIRECTLY (in the same process).
#     No separate server needed, so it deploys as ONE process on free hosts
#     like Streamlit Community Cloud.
#
# It still uses the same database (Supabase) and Gemini, and keeps per-session
# document isolation (session id in the URL).
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

# Import the backend logic DIRECTLY (no HTTP).
from app.pdf_utils import extract_pages
from app.chunking import chunk_pages
from app.vector_store import save_chunks, list_documents
from app.rag import answer_question
from app.conversations import save_conversation, get_recent_history, get_full_history


st.set_page_config(page_title="CareRAG", page_icon="🏥", layout="centered")
st.title("🏥 CareRAG — Healthcare Policy Assistant")
st.caption("Upload your policy / bill / discharge documents and ask questions. "
           "Every answer shows the exact source page.")


# ----------------------------------------------------------------------------
# Session id (per-browser isolation), persisted in the URL so refresh keeps it.
# ----------------------------------------------------------------------------
if "session_id" not in st.session_state:
    existing = st.query_params.get("session")
    if existing:
        st.session_state.session_id = existing
    else:
        new_id = str(uuid.uuid4())
        st.session_state.session_id = new_id
        st.query_params["session"] = new_id

session_id = st.session_state.session_id


# ----------------------------------------------------------------------------
# Load this session's chat history on first load (so refresh restores it).
# ----------------------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []
    try:
        for turn in get_full_history(session_id):
            st.session_state.messages.append(
                {"role": "user", "content": turn["question"], "sources": []}
            )
            st.session_state.messages.append(
                {"role": "assistant", "content": turn["answer"], "sources": turn.get("sources", [])}
            )
    except Exception:
        # If the DB isn't reachable yet, just start empty.
        pass


# ----------------------------------------------------------------------------
# Helper: run the ingestion pipeline on an uploaded file (direct, no HTTP).
# ----------------------------------------------------------------------------
def ingest_file(uploaded_file) -> str:
    """Extract -> chunk -> embed -> store one uploaded PDF. Returns a message."""
    data = uploaded_file.getvalue()
    if len(data) > 10 * 1024 * 1024:
        return f"'{uploaded_file.name}' is larger than 10 MB."
    try:
        pages = extract_pages(data)
    except ValueError as e:
        return f"'{uploaded_file.name}': {e}"
    chunks = chunk_pages(pages)
    save_chunks(uploaded_file.name, chunks, session_id)
    return f"Stored '{uploaded_file.name}' ({len(chunks)} chunks)."


# ----------------------------------------------------------------------------
# Sidebar: upload documents + list this session's documents.
# ----------------------------------------------------------------------------
with st.sidebar:
    st.header("📁 Your documents")

    uploaded = st.file_uploader("Upload PDF(s)", type=["pdf"], accept_multiple_files=True)
    if st.button("Upload", disabled=not uploaded):
        with st.spinner("Reading, chunking, and embedding..."):
            for f in uploaded:
                msg = ingest_file(f)
                if msg.startswith("Stored"):
                    st.success(msg)
                else:
                    st.error(msg)

    st.divider()

    try:
        docs = list_documents(session_id)
    except Exception:
        docs = []
    if docs:
        st.write("In your knowledge base:")
        for d in docs:
            st.write(f"• {d['filename']}  ({d['chunk_count']} chunks)")
    else:
        st.info("No documents yet. Upload a PDF to begin.")

    st.divider()
    st.caption("Your documents are private to this browser session.")


# ----------------------------------------------------------------------------
# Main chat area.
# ----------------------------------------------------------------------------
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])
        for source in message.get("sources", []):
            with st.expander(f"📄 {source['filename']} — page {source['page_number']}"):
                st.write(source["snippet"])

question = st.chat_input("Ask a question about your documents...")

if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.write(question)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                history = get_recent_history(session_id, limit=5)
                result = answer_question(question, session_id=session_id, history=history)
                answer = result["answer"]
                sources = result["sources"]
                # Save this turn (same as the API's /ask does).
                save_conversation(session_id, question, answer, sources)
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
