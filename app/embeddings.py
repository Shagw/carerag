# ============================================================================
# embeddings.py — turn text into "embeddings" (vectors) using a LOCAL model.
#
# "Local" means the model runs inside THIS Python process. No API key, no cost,
# no internet needed after the first download. The model outputs 384 numbers
# per piece of text — that's why our database column is vector(384).
#
# Main functions:
#     embed_texts(["a", "b"])  ->  [[384 numbers], [384 numbers]]   (many texts)
#     embed_text("a question") ->  [384 numbers]                    (one text)
# ============================================================================

from typing import List

# SentenceTransformer is the class that loads and runs the embedding model.
from sentence_transformers import SentenceTransformer


# The model we use. It's small (~90 MB), fast on CPU, and outputs 384-dim vectors.
MODEL_NAME = "all-MiniLM-L6-v2"

# We keep the loaded model here so we only load it ONCE and reuse it.
# It starts as None and gets filled in the first time we need it.
_model = None


def _get_model() -> SentenceTransformer:
    """
    Return the embedding model, loading it the first time it's needed.

    This "lazy loading" avoids reloading the ~90 MB model on every call.
    The first call downloads (once) and loads it; later calls reuse it.
    """
    global _model  # we want to modify the module-level _model variable

    # Only load if we haven't already.
    if _model is None:
        print(f"Loading embedding model '{MODEL_NAME}' (first time may download ~90 MB)...")
        _model = SentenceTransformer(MODEL_NAME)
        print("Embedding model loaded.")

    return _model


def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    Turn a LIST of strings into a LIST of vectors (one vector per string).

    Used at upload time to embed all the chunks of a document at once
    (embedding in a batch is faster than one at a time).
    """
    model = _get_model()

    # model.encode(...) does the actual work.
    #   normalize_embeddings=True  -> scale each vector to length 1, which makes
    #                                 cosine similarity search behave cleanly.
    vectors = model.encode(texts, normalize_embeddings=True)

    # `vectors` comes back as a NumPy array; .tolist() converts it to plain
    # Python lists of floats, which is what we store in the database.
    return vectors.tolist()


def embed_text(text: str) -> List[float]:
    """
    Turn ONE string into ONE vector.

    A small convenience wrapper used at ask time to embed the user's question.
    """
    # Reuse embed_texts by passing a one-item list, then take the first result.
    return embed_texts([text])[0]
