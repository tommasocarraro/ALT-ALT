"""
Dimensions of standard metric deep-groove ball bearings, without asking anyone.

A standard code fixes the size: a 6902 is 15 x 28 x 7 whoever makes it, and seals or shields (2RS, 2Z, LLU, ...)
do not change it. Looking these up in a table is exact, where a web search can land on the wrong page.
Anything this module does not recognise with certainty returns None and is left to the web lookup.
"""
import re
from typing import Optional, Tuple

# (inner diameter, outer diameter, width) in mm
_STANDARD = {
    # 68xx (ISO 618xx), thin section
    "6800": (10, 19, 5), "6801": (12, 21, 5), "6802": (15, 24, 5), "6803": (17, 26, 5),
    "6804": (20, 32, 7), "6805": (25, 37, 7), "6806": (30, 42, 7), "6807": (35, 47, 7),
    # 69xx (ISO 619xx)
    "6900": (10, 22, 6), "6901": (12, 24, 6), "6902": (15, 28, 7), "6903": (17, 30, 7),
    "6904": (20, 37, 9), "6905": (25, 42, 9), "6906": (30, 47, 9), "6907": (35, 55, 10),
    # 60xx
    "6000": (10, 26, 8), "6001": (12, 28, 8), "6002": (15, 32, 9), "6003": (17, 35, 10),
    "6004": (20, 42, 12), "6005": (25, 47, 12), "6006": (30, 55, 13),
    # 62xx
    "6200": (10, 30, 9), "6201": (12, 32, 10), "6202": (15, 35, 11), "6203": (17, 40, 12),
    "6204": (20, 47, 14), "6205": (25, 52, 15),
    # small bores
    "608": (8, 22, 7), "698": (8, 19, 6), "628": (8, 24, 8),
    "609": (9, 24, 7), "699": (9, 20, 6), "629": (9, 26, 8),
}

# suffixes that describe seals, shields, clearance or fill, and leave the outside dimensions untouched
_NEUTRAL_SUFFIXES = {
    "RS", "2RS", "2RS1", "2RSR", "2RSH", "RSR", "RS1", "LLU", "LLB", "LU", "LB", "VV", "DD", "DDU",
    "Z", "2Z", "ZZ", "2ZR", "C3", "CN", "MAX",
}


def _tokens(code: str):
    return [t for t in re.split(r"[\s\-_/.]+", code.upper().strip()) if t]


def standard_dimensions(code: str) -> Optional[Tuple[float, float, float]]:
    """(inner, outer, width) in mm for a standard bearing code, or None if the code is not certainly standard."""
    tokens = _tokens(code)
    if not tokens:
        return None
    base, suffixes = tokens[0], tokens[1:]

    # any marking we do not know (E/EA/EB extended ring, F/FO flange, ...) may change the geometry
    if any(s not in _NEUTRAL_SUFFIXES for s in suffixes):
        return None

    # ISO long form: 61804 is the same bearing as 6804, 61902 the same as 6902
    m = re.fullmatch(r"61([89]\d\d)", base)
    if m:
        base = "6" + m.group(1)
    return _STANDARD.get(base)


def encoded_dimensions(code: str) -> Optional[Tuple[float, float, float]]:
    """
    Some codes spell their own size: 'MR 15267' is 15 x 26 x 7, 'MR 173110' is 17 x 31 x 10.
    Only the unambiguous 5- and 6-digit forms are read.
    A diagram may also give a plain size instead of a code: '17x30x7'.
    """
    size = re.fullmatch(r"(\d+(?:\.\d+)?)[x×*](\d+(?:\.\d+)?)[x×*](\d+(?:\.\d+)?)", re.sub(r"\s+", "", code.lower()))
    if size:
        inner, outer, width = (float(g) for g in size.groups())
        return (inner, outer, width) if inner < outer else None

    tokens = _tokens(code)
    joined = "".join(tokens[:2]) if tokens and tokens[0] == "MR" else (tokens[0] if tokens else "")
    rest = tokens[2:] if tokens and tokens[0] == "MR" else tokens[1:]
    m = re.fullmatch(r"MR(\d\d)(\d\d)(\d{1,2})", joined)
    if not m or any(s not in _NEUTRAL_SUFFIXES for s in rest):
        return None
    inner, outer, width = (int(g) for g in m.groups())
    return (inner, outer, width) if inner < outer else None
