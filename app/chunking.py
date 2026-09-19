# ============================================================================
# chunking.py — split each page's text into smaller, overlapping chunks.
#
# WHY: smaller chunks make vector search more precise, and overlap keeps
# sentences that fall on a boundary from being cut in half.
#
# We keep the PAGE NUMBER on every chunk, so citations still work after
# splitting.
#
# Main function:
#     chunk_pages([(1, "page 1 text"), ...])  ->  [(1, "chunk"), (1, "chunk"), (2, "chunk"), ...]
# ============================================================================

from typing import List, Tuple


# How big each chunk is, measured in WORDS. ~200 words is a good, readable size.
CHUNK_SIZE = 200

# How many words repeat between one chunk and the next (the "overlap").
# 40 words of overlap keeps context flowing across chunk boundaries.
CHUNK_OVERLAP = 40


def _split_text(text: str) -> List[str]:
    """
    Split ONE page's text into overlapping chunks (a private helper).

    The leading underscore in the name is a Python convention meaning
    "this is an internal helper, not meant to be used from outside this file".
    """
    # Break the text into a list of words by splitting on whitespace.
    words = text.split()

    # If the page is short enough to be a single chunk, just return it as-is.
    if len(words) <= CHUNK_SIZE:
        return [text.strip()]

    chunks: List[str] = []

    # `start` marks where the current chunk begins (an index into `words`).
    start = 0

    # Keep making chunks until we've covered all the words.
    while start < len(words):
        # The current chunk is CHUNK_SIZE words starting at `start`.
        end = start + CHUNK_SIZE
        chunk_words = words[start:end]          # a slice of the words list

        # Join those words back into a normal string and save it.
        chunks.append(" ".join(chunk_words))

        # Move the start forward, but step BACK by CHUNK_OVERLAP so the next
        # chunk repeats the last few words of this one (that's the overlap).
        start = end - CHUNK_OVERLAP

    return chunks


def chunk_pages(pages: List[Tuple[int, str]]) -> List[Tuple[int, str]]:
    """
    Turn a list of (page_number, page_text) into a list of
    (page_number, chunk_text) — many chunks per page.

    INPUT (from pdf_utils.extract_pages):
        [(1, "all text of page 1"), (2, "all text of page 2"), ...]

    OUTPUT:
        [(1, "chunk a"), (1, "chunk b"), (2, "chunk a"), ...]
        Each chunk still knows which page it came from.
    """
    result: List[Tuple[int, str]] = []

    # Go through each page and split it, keeping the page number on every chunk.
    for page_number, page_text in pages:
        for chunk in _split_text(page_text):
            # Skip any empty chunk just in case (defensive, keeps data clean).
            if chunk.strip():
                result.append((page_number, chunk))

    return result
