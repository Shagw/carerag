# ============================================================================
# embeddings.py — turn text into "embeddings" (vectors) using the Gemini API.
#
# WHY GEMINI (not a local model)? The local sentence-transformers model pulls
# in PyTorch (~300+ MB RAM), which does not fit on small free hosts (e.g.
# Render's 512 MB free tier). Gemini's embedding API runs server-side, so our
# app stays tiny and deploys on free hosting.
#
# Model: gemini-embedding-001, requested at 768 dimensions (output_dimensionality)
# to keep the database lean. That is why our DB column is vector(768).
#
# We use task_type to improve retrieval quality:
#   - "retrieval_document"  when embedding the stored document chunks
#   - "retrieval_query"     when embedding the user's question
#
# Main functions:
#   embed_texts(texts)  -> list of 768-dim vectors (documents, by default)
#   embed_text(text)    -> one 768-dim vector (query, by default)
# ============================================================================

from typing import List

import google.generativeai as genai

from app.key_manager import key_manager, AllKeysCoolingDown


# The Gemini embedding model and the dimension we request.
MODEL_NAME = "models/gemini-embedding-001"
EMBED_DIM = 768


def _embed_one(text: str, task_type: str) -> List[float]:
    """
    Embed a SINGLE piece of text with Gemini, returning a 768-number vector.

    Uses the key manager so a rate-limited key is skipped for the next one.
    """
    # Try each key at most once (same rotation idea as llm.py).
    for _attempt in range(len(key_manager.keys)):
        try:
            api_key = key_manager.get_key()
        except AllKeysCoolingDown:
            raise RuntimeError("All AI keys are cooling down, please try again in a minute.")

        try:
            genai.configure(api_key=api_key)
            result = genai.embed_content(
                model=MODEL_NAME,
                content=text,
                task_type=task_type,
                output_dimensionality=EMBED_DIM,
            )
            return result["embedding"]
        except Exception as error:
            # If it's a rate-limit, cool the key down and try the next one.
            message = str(error).lower()
            if "429" in message or "quota" in message or "rate" in message or "exhausted" in message:
                key_manager.mark_rate_limited(api_key)
                continue
            raise  # a real error (bad key, network) — surface it

    raise RuntimeError("All AI keys are cooling down, please try again in a minute.")


def embed_texts(texts: List[str], task_type: str = "retrieval_document") -> List[List[float]]:
    """
    Turn a LIST of strings into a LIST of 768-dim vectors.

    Defaults to "retrieval_document" because this is used at upload time to
    embed the document chunks we store.
    """
    return [_embed_one(text, task_type) for text in texts]


def embed_text(text: str, task_type: str = "retrieval_query") -> List[float]:
    """
    Turn ONE string into ONE 768-dim vector.

    Defaults to "retrieval_query" because this is used at ask time to embed
    the user's question.
    """
    return _embed_one(text, task_type)
