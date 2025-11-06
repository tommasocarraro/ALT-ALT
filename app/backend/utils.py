import io
import json
import os
from typing import Tuple
import fitz
import requests


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """
    Use PyMuPDF to extract text per page.
    """
    buf = io.BytesIO(pdf_bytes)
    doc = fitz.open(stream=buf, filetype="pdf")
    pages_text = []
    for i, page in enumerate(doc):
        text = page.get_text("text")
        pages_text.append(f"=== PAGE {i+1} ===\n{text.strip()}")
    doc.close()
    return "\n\n".join(pages_text)


def read_pdf(pdf_url: str) -> Tuple[str, bytes]:
    """
    Downloads a PDF from a URL and extracts textual information from it.
    """
    r = requests.get(pdf_url, timeout=60)
    r.raise_for_status()
    pdf_bytes = r.content

    raw_text = extract_pdf_text(pdf_bytes)

    return raw_text, pdf_bytes


def highlight_pdf(pdf_bytes: bytes, bearings: dict) -> bytes:
    """
    Take PDF bytes and highlight every occurrence of each bearing code.
    Returns the new PDF bytes (does not touch disk).

    :param pdf_bytes: original PDF in bytes
    :param bearings: JSON containing {"bearings": [{"code": "..."}, ...]}
    :return: highlighted PDF bytes
    """
    codes = [b["code"] for b in bearings["bearings"]]

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        for page in doc:
            for code in codes:
                # Case-insensitive search; add TEXT_IGNORECASE flag
                hits = page.search_for(code, quads=True)
                if hits:
                    page.add_highlight_annot(hits)

        new_pdf_bytes = doc.tobytes(deflate=True, clean=True, garbage=4)
        return new_pdf_bytes
    finally:
        doc.close()
