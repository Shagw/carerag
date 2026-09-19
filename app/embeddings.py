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
# PERFORMANCE: we embed a whole LIST of texts in ONE API call (batching). This
# makes uploading a big document fast (one request instead of one-per-chunk)
# and reduces the chance of hitting rate limits.
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

# Friendly message when every key is rate-limited.
ALL_KEYS_BUSY = "All AI keys are cooling down, please try again in a minute."


def _looks_like_rate_limit(error: Exception) -> bool:
    """True if the error is a rate-limit / quota problem."""
    m = str(error).lower()
    return "429" in m or "quota" in m or "rate" in m or "exhausted" in m


def _embed_batch(texts: List[str], task_type: str) -> List[List[float]]:
    """
    Embed a LIST of texts in ONE Gemini call, returning one vector per text.

    Uses the key manager: if a key is rate-limited, cool it down and try the
    next key. Raises RuntimeError if all keys are cooling down.
    """
    for _attempt in range(len(key_manager.keys)):
        try:
            api_key = key_manager.get_key()
        except AllKeysCoolingDown:
            raise RuntimeError(ALL_KEYS_BUSY)

        try:
            genai.configure(api_key=api_key)
            result = genai.embed_content(
                model=MODEL_NAME,
                content=texts,               # a LIST -> Gemini returns a list of vectors
                task_type=task_type,
                output_dimensionality=EMBED_DIM,
            )
            return result["embedding"]       # list of 768-dim vectors
        except Exception as error:
            if _looks_like_rate_limit(error):
                key_manager.mark_rate_limited(api_key)
                continue
            raise

    raise RuntimeError(ALL_KEYS_BUSY)


def embed_texts(texts: List[str], task_type: str = "retrieval_document") -> List[List[float]]:
    """
    Turn a LIST of strings into a LIST of 768-dim vectors, in one batch call.

    Defaults to "retrieval_document" because this is used at upload time to
    embed the document chunks we store.
    """
    if not texts:
        return []
    return _embed_batch(texts, task_type)


def embed_text(text: str, task_type: str = "retrieval_query") -> List[float]:
    """
    Turn ONE string into ONE 768-dim vector.

    Defaults to "retrieval_query" because this is used at ask time to embed
    the user's question.
    """
    # Reuse the batch path with a single-item list, then take the first vector.
    return _embed_batch([text], task_type)[0]
