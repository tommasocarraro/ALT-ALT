import base64
from typing import Callable, Dict, List, Optional, Tuple

from app.backend.llm import prompts
from app.backend.llm.client import ask_structured, research
from app.backend.llm.schemas import DiagramExtraction, DimensionLookup, PartReference, ReferenceResolution
from app.backend.llm.standard_bearings import encoded_dimensions, standard_dimensions
from app.backend.utils import download

# given a bearing code, returns the dimensions already stored for it, or None
KnownDimensions = Callable[[str], Optional[dict]]


def _document_block(data: bytes, media_type: str) -> dict:
    """A PDF goes in as a document (the model sees each page as text and as an image), anything else as an image."""
    kind = "document" if media_type == "application/pdf" else "image"
    return {"type": kind, "source": {"type": "base64", "media_type": media_type,
                                     "data": base64.standard_b64encode(data).decode()}}


def extract_from_documents(documents: List[Tuple[bytes, str]]) -> DiagramExtraction:
    """
    Step 1. Reads the bearing codes, and the bearings that only have a part reference, straight from the diagram.

    :param documents: (bytes, media type) of each file of the diagram: a PDF, or page images
    """
    content = [_document_block(data, media_type) for data, media_type in documents]
    content.append({"type": "text", "text": prompts.EXTRACT})
    return ask_structured(content, DiagramExtraction, prompts.SYSTEM)


def resolve_references(references: List[PartReference], manufacturer: Optional[str], model: Optional[str]) -> ReferenceResolution:
    """Step 2. Looks up on the web the bearing code behind each part reference. Skipped when there are none."""
    if not references:
        return ReferenceResolution(references=[])
    bike = " ".join(x for x in (manufacturer, model) if x) or "bike (manufacturer not stated)"
    listing = "\n".join(
        f"- {r.ref_id}: {r.description}" + (f", part number {r.part_number}" if r.part_number else "")
        for r in references
    )
    findings = research(prompts.RESOLVE.format(bike=bike, references=listing), prompts.SYSTEM)
    items = ", ".join(r.ref_id for r in references)
    text = prompts.STRUCTURE.format(items=items, findings=findings)
    return ask_structured([{"type": "text", "text": text}], ReferenceResolution, prompts.SYSTEM)


def _dimensions(inner, outer, width, extended=None, flange=None) -> dict:
    return {"inner_diameter": inner, "outer_diameter": outer, "width": width,
            "extended_inner_ring_width": extended, "flange_diameter": flange}


def find_dimensions(codes: List[str], known_dimensions: Optional[KnownDimensions] = None) -> Dict[str, dict]:
    """
    Step 3. Dimensions per bearing code, from the most reliable source that has them:
    what is already stored (so a correction made by a person sticks), the standard table, the size spelled in
    the code itself, and only then the web.

    :return: code -> {"dimensions": {...} or None, "source": ..., "source_url": ...}
    """
    out: Dict[str, dict] = {}
    for code in codes:
        stored = known_dimensions(code) if known_dimensions else None
        if stored:
            out[code] = {"dimensions": stored, "source": "database", "source_url": None}
        elif standard_dimensions(code):
            out[code] = {"dimensions": _dimensions(*standard_dimensions(code)), "source": "standard", "source_url": None}
        elif encoded_dimensions(code):
            out[code] = {"dimensions": _dimensions(*encoded_dimensions(code)), "source": "code", "source_url": None}

    missing = [c for c in codes if c not in out]
    if missing:
        findings = research(prompts.DIMENSIONS.format(codes="\n".join(f"- {c}" for c in missing)), prompts.SYSTEM)
        text = prompts.STRUCTURE.format(items=", ".join(missing), findings=findings)
        looked_up = ask_structured([{"type": "text", "text": text}], DimensionLookup, prompts.SYSTEM)
        by_code = {b.code: b for b in looked_up.bearings}
        for code in missing:
            b = by_code.get(code)
            complete = b is not None and None not in (b.inner_diameter, b.outer_diameter, b.width)
            out[code] = {
                "dimensions": _dimensions(b.inner_diameter, b.outer_diameter, b.width,
                                          b.extended_inner_ring_width, b.flange_diameter) if complete else None,
                "source": "web" if complete else None,
                "source_url": b.source_url if complete else None,
            }
    return out


def analyse_diagram(documents: List[Tuple[bytes, str]], known_dimensions: Optional[KnownDimensions] = None) -> dict:
    """
    Runs the three steps on a diagram and returns everything found, with where each answer came from.

    :return: {
        "manufacturer", "model",
        "bearings": [{"code", "quantity", "found_in": "diagram" | "web", "reference", "source_url",
                      "dimensions": {...} | None, "dimensions_source", "dimensions_source_url"}],
        "unresolved_references": [{"description", "part_number", "note"}],
    }
    """
    extraction = extract_from_documents(documents)
    resolution = resolve_references(extraction.unresolved_references, extraction.manufacturer, extraction.model)
    resolved = {r.ref_id: r for r in resolution.references}

    bearings: Dict[str, dict] = {}
    for b in extraction.bearings:
        bearings.setdefault(b.code, {"code": b.code, "quantity": b.quantity, "found_in": "diagram",
                                     "reference": b.label, "source_url": None})

    unresolved = []
    for ref in extraction.unresolved_references:
        r = resolved.get(ref.ref_id)
        label = ref.part_number or ref.description
        if r and r.bearing_code:
            bearings.setdefault(r.bearing_code, {"code": r.bearing_code, "quantity": ref.quantity, "found_in": "web",
                                                 "reference": label, "source_url": r.source_url})
        else:
            unresolved.append({"description": ref.description, "part_number": ref.part_number,
                               "note": r.note if r else None})

    dims = find_dimensions(list(bearings), known_dimensions)
    for code, b in bearings.items():
        b["dimensions"] = dims[code]["dimensions"]
        b["dimensions_source"] = dims[code]["source"]
        b["dimensions_source_url"] = dims[code]["source_url"]

    return {
        "manufacturer": extraction.manufacturer,
        "model": extraction.model,
        "bearings": list(bearings.values()),
        "unresolved_references": unresolved,
    }


def from_url_to_bearings(url: str, known_dimensions: Optional[KnownDimensions] = None) -> Tuple[dict, bytes]:
    """
    Takes the URL of an exploded diagram and returns what `analyse_diagram` finds in it, plus the PDF content.

    :param url: url to the PDF of the exploded diagram
    :param known_dimensions: lookup of dimensions already stored for a bearing code
    """
    pdf_content = download(url)
    return analyse_diagram([(pdf_content, "application/pdf")], known_dimensions), pdf_content
