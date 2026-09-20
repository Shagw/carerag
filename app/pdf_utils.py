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

import re
# "List" and "Tuple" are type hints that describe the shape of our data:
# a list of (page_number, text) tuples.
from typing import List, Tuple


def _clean_text(text: str) -> str:
    """
    Tidy up raw extracted text so chunks and citation snippets read cleanly.

    - remove control / zero-width characters (pure junk like \\x03 \\x18 \\x89
      that some PDFs emit around decorative fonts)
    - collapse repeated whitespace and blank lines

    NOTE: we do NOT try to "unscramble" words from PDFs that use a broken font
    encoding (where e.g. "Treatment" is stored as "$u;-|l;m|"). That text is not
    recoverable without OCR, which we intentionally don't do (keeps the app
    lightweight/free). See the README's limitations note.
    """
    # Drop control chars (except normal whitespace \n \t) and zero-width chars.
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\u200b-\u200f\ufeff]", "", text)
    # Normalise line endings.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Collapse 3+ newlines into a paragraph break; runs of spaces into one.
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def _readable_ratio(text: str) -> float:
    """
    Fraction of characters that are normal readable ones (letters, digits,
    spaces, common punctuation). Used only to skip pages that are ALMOST
    ENTIRELY junk — partially-garbled pages are kept, because their readable
    portion is still useful.
    """
    if not text:
        return 0.0
    readable = sum(
        1 for ch in text
        if ch.isascii() and (ch.isalnum() or ch.isspace() or ch in ".,;:!?()'\"-/%$&")
    )
    return readable / len(text)


def extract_pages(pdf_bytes: bytes) -> List[Tuple[int, str]]:
    """
    Extract the text of each page from a PDF given as raw bytes.

    INPUT:
        pdf_bytes: the PDF file's contents in memory (what an upload gives us).

    OUTPUT:
        A list of (page_number, text) pairs, where page_number starts at 1.
        Blank pages and pages that are almost entirely un-decodable are skipped;
        partially-garbled pages are kept (their readable text is still useful).

    RAISES:
        ValueError: if the file can't be opened as a PDF, or if the whole
                    document has NO usable text (e.g. a scanned image — we don't
                    do OCR, so we ask for a text-based PDF instead).
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
        # Pull the plain text out of this page, then clean it up.
        text = _clean_text(page.get_text())

        # Keep the page unless it's blank OR almost entirely junk (< 30%
        # readable — that means the font is essentially undecodable on this
        # page). Partially-garbled pages (e.g. 80% readable) are kept.
        if text and _readable_ratio(text) >= 0.30:
            human_page_number = page_index + 1
            pages.append((human_page_number, text))

    # Always close the PDF to free memory.
    pdf.close()

    # If we collected NOTHING usable, the PDF is a scanned image (no text) or its
    # fonts are entirely undecodable. We don't do OCR, so we tell the user.
    if not pages:
        raise ValueError(
            "This PDF has no readable text (it may be a scanned image or use "
            "fonts we can't decode). Please upload a text-based PDF."
        )

    return pages
