# ============================================================================
# pdf_utils.py — read a PDF and pull out its text, page by page.
#
# The IMPORTANT part: we keep the PAGE NUMBER next to each piece of text.
# That page number is what lets us show citations like "policy.pdf — page 12"
# later on.
#
# Main function:
#     extract_pages(pdf_bytes)  ->  [(1, "text of page 1"), (2, "text of page 2"), ...]
# ============================================================================

# PyMuPDF is installed as "PyMuPDF" but imported as "fitz". (Historical name.)
import fitz

# "List" and "Tuple" are type hints that describe the shape of our data:
# a list of (page_number, text) tuples.
from typing import List, Tuple


def extract_pages(pdf_bytes: bytes) -> List[Tuple[int, str]]:
    """
    Extract the text of each page from a PDF given as raw bytes.

    INPUT:
        pdf_bytes: the PDF file's contents in memory (what an upload gives us).

    OUTPUT:
        A list of (page_number, text) pairs, where page_number starts at 1.
        Pages that contain no text are skipped (e.g. a blank page).

    RAISES:
        ValueError: if the file can't be opened as a PDF, or if the whole
                    document has NO extractable text (likely a scanned image —
                    we don't do OCR, so we ask for a text-based PDF instead).
    """

    # Try to open the PDF from the in-memory bytes.
    # stream=... means "read from these bytes" (instead of a file path).
    # We wrap this in try/except so a broken/non-PDF file gives a clear error.
    try:
        pdf = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception:
        # If fitz can't open it, it's not a valid PDF we can read.
        raise ValueError("Could not open the file as a PDF. Please upload a valid PDF.")

    # This is where we collect our (page_number, text) results.
    pages: List[Tuple[int, str]] = []

    # Loop over every page. `enumerate` gives us both the position and the page.
    # page_index starts at 0, so the human page number is page_index + 1.
    for page_index, page in enumerate(pdf):
        # Pull the plain text out of this page.
        text = page.get_text()

        # `.strip()` removes leading/trailing whitespace. If nothing is left,
        # the page had no real text (blank page or an image), so we skip it.
        if text.strip():
            human_page_number = page_index + 1
            pages.append((human_page_number, text))

    # Always close the PDF to free memory.
    pdf.close()

    # If we collected NOTHING, the PDF had no extractable text anywhere.
    # That usually means it's a scanned/image PDF. We don't do OCR, so we tell
    # the user clearly instead of silently storing an empty document.
    if not pages:
        raise ValueError(
            "This PDF has no extractable text. It may be a scanned image. "
            "Please upload a text-based PDF."
        )

    return pages
