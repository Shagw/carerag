# ============================================================================
# rag.py — the RAG pipeline: turn a question into a grounded answer + citations.
#
# This is the "brain" that connects the other pieces:
#   embeddings  -> turn the question into a vector
#   vector_store-> find the closest chunks
#   (guard)     -> if nothing is relevant enough, say "I don't know"
#   llm         -> ask Gemini to answer using ONLY those chunks
#   (citations) -> attach document + page + snippet for each source
#
# Main function:
#     answer_question(question, history) -> {"answer": str, "sources": [...]}
# ============================================================================

from typing import List, Dict, Any, Tuple

from app.config import settings
from app.embeddings import embed_text
from app.vector_store import search
from app.llm import generate_answer


# The polite refusal we return when the documents don't contain the answer.
I_DONT_KNOW = "I don't know based on the provided documents."


def _build_prompt(
    question: str,
    chunks: List[Dict[str, Any]],
    history: List[Tuple[str, str]],
) -> str:
    """
    Build the text prompt we send to Gemini.

    It contains three parts:
      1. strict instructions (answer ONLY from the context, else say I don't know)
      2. the retrieved chunks (the "context"), each labeled with its source
      3. recent chat history + the current question
    """
    # --- 1) Instructions that keep the model honest. ---
    instructions = (
        "You are CareRAG, a helpful assistant for healthcare and insurance documents.\n"
        "Answer the user's question using ONLY the context below.\n"
        "If the answer is not in the context, reply exactly: "
        f"\"{I_DONT_KNOW}\"\n"
        "Do not make up information. Be clear and concise.\n"
    )

    # --- 2) The retrieved chunks, each tagged with its document and page. ---
    # Tagging each chunk helps the model (and us) keep track of sources.
    context_parts = []
    for i, chunk in enumerate(chunks, start=1):
        context_parts.append(
            f"[Source {i}: {chunk['filename']}, page {chunk['page_number']}]\n"
            f"{chunk['content']}"
        )
    context = "\n\n".join(context_parts)

    # --- 3) Recent conversation history (for follow-up questions). ---
    # We include prior turns so questions like "and for children?" make sense.
    history_text = ""
    for past_question, past_answer in history:
        history_text += f"User: {past_question}\nAssistant: {past_answer}\n"

    # Put it all together into one prompt string.
    prompt = (
        f"{instructions}\n"
        f"=== CONTEXT ===\n{context}\n\n"
        f"=== CONVERSATION SO FAR ===\n{history_text}\n"
        f"=== CURRENT QUESTION ===\n{question}\n\n"
        f"Answer:"
    )
    return prompt


def _make_citations(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Turn the retrieved chunks into citation entries for the response.
    Each citation shows the document, the page, and a short snippet.
    """
    citations = []
    for chunk in chunks:
        # Keep the snippet short so the UI stays tidy (first ~300 characters).
        snippet = chunk["content"].strip().replace("\n", " ")
        if len(snippet) > 300:
            snippet = snippet[:300] + "..."

        citations.append(
            {
                "filename": chunk["filename"],
                "page_number": chunk["page_number"],
                "snippet": snippet,
            }
        )
    return citations


def answer_question(
    question: str,
    session_id: str,
    history: List[Tuple[str, str]] = None,
) -> Dict[str, Any]:
    """
    The full RAG pipeline for one question.

    INPUT:
        question:   the user's question.
        session_id: only search THIS session's documents (per-session isolation).
        history:    optional list of previous (question, answer) pairs for
                    follow-up context. Defaults to empty.

    OUTPUT:
        {
          "answer": "the answer text (or the 'I don't know' message)",
          "sources": [ {filename, page_number, snippet}, ... ]   # empty if unknown
        }
    """
    # If no history was passed, use an empty list.
    if history is None:
        history = []

    # 1) Turn the question into a vector.
    #    For FOLLOW-UP questions, the question alone can be too vague to search
    #    well (e.g. "how many hours?"). So if we have history, we prepend the
    #    most recent PREVIOUS question to give retrieval some context. This is
    #    called "history-aware retrieval".
    if history:
        previous_question = history[-1][0]           # the last question asked
        search_query = previous_question + " " + question
    else:
        search_query = question
    question_vector = embed_text(search_query)

    # 2) Find the most similar chunks within THIS session's documents.
    chunks = search(question_vector, top_k=settings.top_k, session_id=session_id)

    # 3) STRICT GUARD: if we found nothing, or the closest chunk is farther than
    #    our threshold, the documents don't contain the answer. Say so and stop
    #    (we don't even call Gemini — saves an API call and prevents guessing).
    if not chunks or chunks[0]["distance"] > settings.similarity_threshold:
        return {"answer": I_DONT_KNOW, "sources": []}

    # 4) Build the prompt from the chunks + history + question.
    prompt = _build_prompt(question, chunks, history)

    # 5) Ask Gemini to write the answer.
    answer = generate_answer(prompt)

    # 6) Attach citations (document + page + snippet) from the chunks we used.
    #    BUT: if Gemini itself decided the context doesn't answer the question
    #    and replied "I don't know", we should NOT show citations — sources
    #    should only back up a REAL answer, not a refusal. So we check the
    #    answer text and return empty sources in that case.
    if I_DONT_KNOW.lower() in answer.strip().lower():
        return {"answer": I_DONT_KNOW, "sources": []}

    sources = _make_citations(chunks)

    return {"answer": answer, "sources": sources}
