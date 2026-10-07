import fitz
import requests


def download(url: str) -> bytes:
    """
    Downloads a file (the PDF of an exploded diagram) from a URL.
    """
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return r.content


def highlight_pdf(pdf_bytes: bytes, bearings: dict) -> bytes:
    """
    Take PDF bytes and highlight every occurrence of each bearing code.
    Returns the new PDF bytes (does not touch disk).

    :param pdf_bytes: original PDF in bytes
    :param bearings: dict containing {"bearings": [{"code": "..."}, ...]}
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
