import json
import os
from typing import Tuple

from app.backend.llm.utils import get_bearings
from app.backend.utils import read_pdf

def from_url_to_bearings(url: str) -> Tuple[dict, bytes]:
    """
    This function takes the URL of an exploded diagram in input and calls an LLM to extract
    bearing codes from the text of the PDF. In addition, it looks the web for the dimensions of these bearings.
    It returns a JSON file with the bearings extracted, plus the content of the PDF.

    :param url: url to the PDF of the exploded diagram
    :return: list of bearings with their dimensions and PDF content
    """
    raw_text, pdf_content = read_pdf(url)
    bearings = get_bearings(raw_text)
    return json.loads(bearings), pdf_content
