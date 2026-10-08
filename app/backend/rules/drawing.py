"""
Draws one job of the rule engine as a section view: the whole part as it is when the job starts (every bearing,
spacer and axle still in it), cut through the middle, with the tool pieces in the order of the engine's `stack`.
The part never turns between the drawings of one arrangement: side A (the disc side of a hub) is on the left,
side B on the right, and the open end of a single seat on the right. The tool is what changes sides, and the pink
arrow shows which way the bearing being worked on travels.

Diameters are to scale (they come from the bearing and from the piece sizes); lengths are only indicative,
because the real lengths of the pieces are not in the catalogue.
Pieces are coloured by what they are made of: acetal black, aluminium gold, steel grey.
Each piece carries the letter it has in the written instructions (a, b, c, ... in stack order), so the drawing
needs no text of its own.
"""
import math
from typing import List, Optional, Tuple

PX = 4.0            # pixels per millimetre
STUD_R = 4.0        # M8 stud
DEFAULT = {"inner": 15.0, "outer": 28.0, "width": 7.0}     # drawn when a bearing's dimensions are unknown

# indicative lengths, in millimetres
LEN = {"drift_re": 16, "sleeve": 30, "sleeve_6": 30, "sleeve_long": 36, "oa_drift": 44, "spacer_tube": 45,
       "pilot_short": 6, "pilot_long": 18, "handle": 14, "stud_stop": 12, "stop_ctr": 16, "alt_drift": 8,
       "spacer": 24, "axle": 34, "body": 10}
RELIEF = 3.0        # depth of the recess on one face of a Drift RE

ACETAL, ALUMINIUM, STEEL, DARK_STEEL = "#262626", "#e0b021", "#9aa0a6", "#4b5563"
LINE, LINE_ON_BLACK = "#1f2933", "#d1d5db"
PART, SPACER, AXLE, RING, BALL, MOVE = "#b6c0da", "#dfe3ea", "#eef0f4", "#8f979d", "#f8fafc", "#d6249f"
# pieces that exist in one material only
ONLY_ACETAL = {"stop_ctr", "stop_oal", "sleeve_6", "oa_drift"}
ONLY_ALUMINIUM = {"alt_drift", "alt_rod", "alt_extractor", "handle"}
HOSTS = ("bearing", "bearing_in_part", "other_bearing", "axle")     # things a pilot can sit inside

BADGE_R = 13.0      # radius of a letter badge, in pixels
BADGE_GAP = 2 * BADGE_R + 6


class _Canvas:
    def __init__(self) -> None:
        self.shapes: List[str] = []
        self.labels: List[Tuple[float, float, str, bool]] = []     # target x, target y, letter, size still open?
        self.marks: List[Tuple[float, float]] = []                 # where a "turn this" sign goes
        self.max_r = 0.0

    @staticmethod
    def _stroke(colour: str) -> str:
        return LINE_ON_BLACK if colour == ACETAL else LINE

    def ring(self, x: float, length: float, r_in: float, r_out: float, colour: str, shift: float = 0.0) -> None:
        """A tube cut lengthwise: one rectangle above the axis, one below (a single one when r_in is 0)."""
        self.max_r = max(self.max_r, r_out + abs(shift))
        spans = [(-r_out, 2 * r_out)] if r_in <= 0 else [(-r_out, r_out - r_in), (r_in, r_out - r_in)]
        for y, height in spans:
            self.shapes.append(
                f'<rect x="{x * PX:.1f}" y="{(y + shift) * PX:.1f}" width="{length * PX:.1f}" height="{height * PX:.1f}" '
                f'fill="{colour}" stroke="{self._stroke(colour)}" stroke-width="0.8"/>')

    def profile(self, points: List[Tuple[float, float]], colour: str) -> None:
        """A shape given by its outline above the axis, drawn there and mirrored below."""
        self.max_r = max(self.max_r, max(r for _, r in points))
        for s in (-1, 1):
            self.shapes.append('<polygon points="' + " ".join(f"{px * PX:.1f},{s * r * PX:.1f}" for px, r in points) +
                               f'" fill="{colour}" stroke="{self._stroke(colour)}" stroke-width="0.8"/>')

    def lines(self, x: float, length: float, r: float, count: int, colour: str = LINE) -> None:
        """Grooves or knurling across a solid piece."""
        for k in range(1, count + 1):
            gx = (x + length * k / (count + 1)) * PX
            self.shapes.append(f'<line x1="{gx:.1f}" y1="{-r * PX:.1f}" x2="{gx:.1f}" y2="{r * PX:.1f}" stroke="{colour}" stroke-width="0.8"/>')

    def handle(self, x: float, colour: str) -> float:
        """The Handle, seen from the side: a bar across the Stud with a hexagonal hub in its middle."""
        length, hub_r, bar_r, reach = LEN["handle"], 7.5, 4.2, 30.0
        mid = x + length / 2
        self.shapes.append(
            f'<rect x="{(mid - bar_r) * PX:.1f}" y="{-reach * PX:.1f}" width="{2 * bar_r * PX:.1f}" height="{2 * reach * PX:.1f}" '
            f'rx="{bar_r * PX:.1f}" fill="{colour}" stroke="{LINE}" stroke-width="0.8"/>')
        # the hub, wider than the bar and chamfered towards it, with the threaded hole the Stud goes through
        pts = [(x, 0), (x, hub_r - 2.5), (x + 3, hub_r), (x + length - 3, hub_r), (x + length, hub_r - 2.5), (x + length, 0)]
        self.profile(pts, colour)
        self.max_r = max(self.max_r, reach)
        return reach

    def stud_stop(self, x: float, colour: str) -> float:
        """The Stud Stop: its narrow boss towards the tool, the wide knurled wheel on the outside."""
        wheel, boss, r = 8.0, LEN["stud_stop"] - 8.0, 13.0
        self.ring(x, boss, STUD_R, 8.0, colour)
        self.ring(x + boss, wheel, STUD_R, r, colour)
        for s in (-1, 1):                      # the knurling runs along the axis
            for k in range(1, 6):
                y = s * (STUD_R + (r - STUD_R) * k / 6) * PX
                self.shapes.append(f'<line x1="{(x + boss) * PX:.1f}" y1="{y:.1f}" x2="{(x + boss + wheel) * PX:.1f}" y2="{y:.1f}" '
                                   f'stroke="{LINE_ON_BLACK}" stroke-width="0.6"/>')
        return r

    def o_ring(self, x: float) -> None:
        """An O-ring on the Stud, seen from the side: a thin black band around it (a dot would read as a ball)."""
        half, reach = 0.7, STUD_R + 0.8
        self.shapes.append(f'<rect x="{(x - half) * PX:.1f}" y="{-reach * PX:.1f}" width="{2 * half * PX:.1f}" '
                           f'height="{2 * reach * PX:.1f}" rx="{half * PX:.1f}" fill="#111827"/>')

    def allen_key(self, x: float, outward: int) -> None:
        """An L-shaped key in the end of a piece; `outward` is -1 when the end faces left, +1 when it faces right."""
        tip, corner = (x - outward * 7) * PX, (x + outward * 7) * PX
        self.shapes.append(f'<path d="M{tip:.1f},0 L{corner:.1f},0 L{corner:.1f},{-24 * PX:.1f}" fill="none" '
                           f'stroke="{DARK_STEEL}" stroke-width="{1.6 * PX:.1f}" stroke-linejoin="round" stroke-linecap="round"/>')
        self.max_r = max(self.max_r, 25)
        self.turn(x + outward * 7, 25)

    def long_key(self, tip: float, out: float) -> None:
        """The Allen key the other way round: its long arm reaches through the part to a bolt deep inside."""
        self.shapes.append(f'<path d="M{tip * PX:.1f},0 L{out * PX:.1f},0 L{out * PX:.1f},{-14 * PX:.1f}" fill="none" '
                           f'stroke="{DARK_STEEL}" stroke-width="{1.6 * PX:.1f}" stroke-linejoin="round" stroke-linecap="round"/>')
        self.max_r = max(self.max_r, 15)
        self.turn(out, 15)

    def turn(self, x: float, r: float) -> None:
        """Marks the piece that is turned."""
        self.marks.append((x * PX, -(r + 1.5) * PX))
        self.max_r = max(self.max_r, r + 8)

    def label(self, x: float, r: float, index: int, above: bool, resolved: bool = True) -> None:
        """A letter pointing at the surface of something, at radius r above or below the axis."""
        self.labels.append((x * PX, (-r if above else r) * PX, chr(97 + index), not resolved))


def _thread(x1: float, x2: float) -> str:
    """The Stud, hatched like a thread. Plain lines, not a pattern: the PDF renderer does not draw patterns."""
    r, pitch = STUD_R * PX, 5.0
    box = f'x="{x1 * PX:.1f}" y="{-r:.1f}" width="{(x2 - x1) * PX:.1f}" height="{2 * r:.1f}"'
    turns = int(((x2 - x1) * PX - pitch) // pitch) + 1
    hatch = "".join(f"M{x1 * PX + k * pitch:.1f},{r:.1f} l{pitch:.1f},{-2 * r:.1f}" for k in range(max(turns, 0)))
    return (f'<rect {box} fill="#d9d2ca" stroke="{LINE}" stroke-width="0.8"/>'
            f'<path d="{hatch}" fill="none" stroke="#6b7280" stroke-width="1.1"/>')


def _turn_sign(cx: float, cy: float) -> str:
    """A clockwise arrow, in pixels. Drawn, not typed: a "↻" character depends on the fonts of whoever shows it."""
    r = 8.0
    at = lambda deg, k=r: (cx + k * math.cos(math.radians(deg)), cy + k * math.sin(math.radians(deg)))
    (x0, y0), (x1, y1) = at(-30), at(225)
    head = [at(262, r), at(218, r - 5), at(218, r + 5)]
    return (f'<path d="M{x0:.1f},{y0:.1f} A{r},{r} 0 1 1 {x1:.1f},{y1:.1f}" fill="none" stroke="{MOVE}" stroke-width="2.4"/>'
            '<polygon points="' + " ".join(f"{x:.1f},{y:.1f}" for x, y in head) + f'" fill="{MOVE}"/>')


def _bearing(c: _Canvas, x: float, d: dict) -> float:
    inner, outer, width = d["inner"] / 2, d["outer"] / 2, d["width"]
    c.ring(x, width, inner, outer, "#c9ced3")                     # the space between the rings
    c.ring(x, width, inner, inner + 1.3, RING)
    c.ring(x, width, outer - 1.3, outer, RING)
    r = min((outer - inner) / 2 - 1.0, width / 2 - 0.7)             # the ball, sitting a little into both rings
    if r > 0.5:
        for s in (-1, 1):
            c.shapes.append(f'<circle cx="{(x + width / 2) * PX:.1f}" cy="{s * (inner + outer) / 2 * PX:.1f}" '
                            f'r="{r * PX:.1f}" fill="{BALL}" stroke="{LINE}" stroke-width="1"/>')
    return width


def _drift(c: _Canvas, x: float, r: float, colour: str, relief: Optional[str]) -> None:
    """A Drift RE: flat on one face, with a 3 mm recess on the other (`relief` says which face, if it shows)."""
    length, lip = LEN["drift_re"], max(r - 2.5, STUD_R + 0.8)
    if relief == "left":
        pts = [(x + RELIEF, STUD_R), (x + RELIEF, lip), (x, lip), (x, r), (x + length, r), (x + length, STUD_R)]
    elif relief == "right":
        end = x + length
        pts = [(x, STUD_R), (x, r), (end, r), (end, lip), (end - RELIEF, lip), (end - RELIEF, STUD_R)]
    else:
        pts = [(x, STUD_R), (x, r), (x + length, r), (x + length, STUD_R)]
    c.profile(pts, colour)


def _step(c: _Canvas, x: float, sleeve_inner: float, sleeve_outer: float, colour: str) -> float:
    """The Step: a stack of shoulders, so that one piece centres every sleeve. Two sit inside the sleeve's end."""
    radii = [max(sleeve_inner - 3.5, STUD_R + 1.5), sleeve_inner - 0.3, sleeve_outer + 1, sleeve_outer + 3.5, sleeve_outer + 6]
    for k, r in enumerate(radii):
        c.ring(x + (k - 2) * 3, 3, STUD_R, r, colour)
    return 9.0                      # only the three outer shoulders add length to the row


def _part(c: _Canvas, segments: List[Tuple[float, float, float]], r_out: float) -> None:
    """The bike part as one shape: a body of constant outside, with the bore stepping from seat to seat."""
    if not segments:
        return
    pts = [(segments[0][0], r_out), (segments[-1][1], r_out)]
    for x0, x1, r_in in reversed(segments):
        pts += [(x1, r_in), (x0, r_in)]
    c.profile(pts, PART)


def _size(item: dict, fallback: float) -> float:
    try:
        return float(item["size"])
    except (TypeError, ValueError):
        return fallback


def _colour(item: dict, job_material: str) -> str:
    piece = item["piece"]
    if piece == "nut":
        return STEEL
    if piece == "stud_stop":
        return ACETAL                   # black oxide steel
    if piece in ONLY_ACETAL:
        return ACETAL
    if piece in ONLY_ALUMINIUM:
        return ALUMINIUM
    return ACETAL if (item.get("material") or job_material) == "Acetal" else ALUMINIUM


def _spread(wanted: List[float], lo: float, hi: float) -> List[float]:
    """Positions as close as possible to the wanted ones (given sorted), at least a badge apart, inside lo..hi."""
    pos = list(wanted)
    for i in range(len(pos)):
        pos[i] = max(pos[i], lo if i == 0 else pos[i - 1] + BADGE_GAP)
    for i in range(len(pos) - 1, -1, -1):
        pos[i] = min(pos[i], hi if i == len(pos) - 1 else pos[i + 1] - BADGE_GAP)
    return pos


def _length(item: dict) -> float:
    """Room a piece takes along the Stud."""
    piece = item["piece"]
    if piece in ("pilot_short", "pilot_long") and item["role"] == "center":
        return 0.0
    return {"nut": 6, "pilot_short": 8, "step": 9, "stop_oal": 36, "alt_rod": 14}.get(piece, LEN.get(piece, 8))


def _axis(scene: dict, removing: bool, fallback: dict) -> List[dict]:
    """
    The seats and what lies between them, left to right, as the tool is laid out: with the bearing being worked on
    travelling to the right, so its seat on the right of the part on a removal and on the left on an install.
    `_mirrored` says when that is the part seen from behind.
    """
    slots, worked = scene["slots"], list(scene["worked"])

    def seats(index: int, outer_first: bool) -> List[dict]:
        items = [{"kind": "seat", "dims": b["dimensions"] or fallback, "present": b["present"],
                  "worked": [index, k] == worked} for k, b in enumerate(slots[index])]      # deepest first
        return items[::-1] if outer_first else items

    if len(slots) == 1:
        elems = seats(0, outer_first=not removing)
    else:
        mine, theirs = worked[0], 1 - worked[0]
        left, right = (theirs, mine) if removing else (mine, theirs)
        elems = seats(left, True) + [{"kind": "middle", "what": scene["middle"], "is": scene["middle_kind"]}] + seats(right, False)
    if not any(e.get("worked") for e in elems):     # no bearing was selected for this seat
        seat = {"kind": "seat", "dims": fallback, "present": removing, "worked": True}
        elems = elems + [seat] if removing else [seat] + elems
    return elems


def _mirrored(scene: dict, removing: bool) -> bool:
    """
    Whether the layout of `_axis` shows the part the wrong way round. The part is always seen from the same
    side: side A on the left and side B on the right, or the open end of a single seat on the right.
    """
    if len(scene["slots"]) == 1:
        return not removing
    return removing == (scene["worked"][0] == 0)


def svg_for(job: dict) -> str:
    """The job as a standalone SVG image."""
    d = job.get("bearing_dimensions") or DEFAULT
    material = job.get("material") or "Aluminum"
    stack = job["stack"]
    removing = job.get("operation") != "install"
    scene = job.get("scene") or {"slots": [[{"dimensions": d, "present": removing}]], "middle": None,
                                 "middle_kind": None, "worked": [0, 0], "protrudes": False}
    pieces = {item["piece"] for item in stack}
    alt_drift_job, extractor_job = "alt_drift" in pieces, "alt_extractor" in pieces
    axle_in = scene["middle"] == "axle"
    c = _Canvas()

    # ---- the part, left to right
    elems = _axis(scene, removing, d)
    for e in elems:
        e["len"] = e["dims"]["width"] if e["kind"] == "seat" else LEN["axle" if e["is"] == "axle" else "spacer"]
    wi = next(i for i, e in enumerate(elems) if e.get("worked"))
    left_len = sum(e["len"] for e in elems[:wi])
    part_r = max(e["dims"]["outer"] for e in elems if e["kind"] == "seat") / 2 + 7

    # ---- which tool pieces come before the part, which after, and which sit inside it
    work = [i for i, item in enumerate(stack) if item["kind"] == "workpiece"]
    first, last = (work[0], work[-1]) if work else (len(stack), len(stack))
    sequential = lambda i: not (stack[i]["piece"] in ("pilot_short", "pilot_long") and stack[i]["role"] == "center") \
        and stack[i]["piece"] not in ("alt_drift", "alt_extractor") and stack[i]["kind"] == "piece"
    before = [i for i in range(first) if sequential(i)]
    after = [i for i in range(last + 1, len(stack)) if sequential(i)]
    # on a push-out the drift works from inside the part, through the seat that is already empty
    inside = removing and not alt_drift_job and not extractor_job and not axle_in

    sleeve = {"inner": d["outer"] / 2 + 0.5, "outer": d["outer"] / 2 + 3.5}
    state = {"rod_from": None}

    def draw(i: int, x: float, side: str) -> float:
        item = stack[i]
        piece, colour, start, top = item["piece"], _colour(item, material), x, 6.5
        if piece == "nut":
            c.ring(x, 6, STUD_R, 6.5, colour); x += 6
        elif piece == "handle":
            top = c.handle(x, colour)
            x += LEN["handle"]
            c.turn(start + LEN["handle"] / 2 + 11, top - 9)      # beside the bar, not on the label's leader
        elif piece == "stud_stop":
            top = c.stud_stop(x, colour); x += LEN["stud_stop"]
        elif piece == "drift_re":
            top = _size(item, d["outer"]) / 2
            # pressing: flat face on the bearing, recess away from it; leveraging: recess towards the part,
            # which is where the bearing and the pilot need the room
            relief = "left" if side == "before" or item["role"] == "leverage" else "right"
            if "relief side towards the bearing" in (item.get("text") or ""):
                relief = "right"
            _drift(c, x, top, colour, relief); x += LEN["drift_re"]
        elif piece == "pilot_short":      # used as a pressing piece on the end of an axle
            top = _size(item, d["inner"]) / 2
            c.ring(x, 8, STUD_R, top, colour); x += 8
        elif piece in ("sleeve", "sleeve_6", "sleeve_long"):
            sleeve["inner"] = {"sleeve": _size(item, d["outer"]) / 2 + 0.5, "sleeve_6": 19.0, "sleeve_long": 18.0}[piece]
            top = sleeve["outer"] = sleeve["inner"] + (3 if piece == "sleeve" else 5)
            c.ring(x, LEN[piece], sleeve["inner"], top, colour); x += LEN[piece]
        elif piece == "step":
            top = sleeve["outer"] + 6
            x += _step(c, x, sleeve["inner"], sleeve["outer"], colour)
        elif piece == "stop_ctr":
            top = 25
            c.profile([(x, STUD_R), (x, 7), (x + LEN["stop_ctr"] * 0.45, top), (x + LEN["stop_ctr"], top),
                       (x + LEN["stop_ctr"], STUD_R)], colour)
            x += LEN["stop_ctr"]
        elif piece == "stop_oal":
            top = 17
            c.ring(x, 30, 12, top, colour)
            c.ring(x + 30, 6, STUD_R, top, colour); x += 36
        elif piece == "spacer_tube":
            top = 6
            c.ring(x, LEN["spacer_tube"], STUD_R, top, colour); x += LEN["spacer_tube"]
        elif piece == "alt_rod":
            # the rod runs on through the far bearing and the spacer; only its outer end is drawn here
            top, state["rod_from"] = 5.5, x
            c.allen_key(x, outward=-1)
            x += 14
        elif piece == "oa_drift":
            try:
                inner, top = (float(v) / 2 for v in str(item["size"]).split("x"))
            except ValueError:
                inner, top = d["inner"] / 2, d["outer"] / 2
            c.ring(x, LEN["oa_drift"], inner, top, colour); x += LEN["oa_drift"]
        else:
            top = 8
            c.ring(x, 8, STUD_R, top, STEEL); x += 8
        c.label(start + 7 if piece == "alt_rod" else (start + x) / 2, top, i, above=True, resolved=item["resolved"])
        return x

    # ---- pieces before the part
    lead = sum(_length(stack[i]) for i in before)
    x = 18.0 if alt_drift_job else (16.0 if left_len else 30.0) if extractor_job else 6.0 + (max(0.0, left_len - lead + 4) if inside else 0.0)
    for i in before:
        x = draw(i, x, "before")

    # ---- where the part starts, and the new bearing waiting in front of it on an install
    protrusion = 10.0 if scene.get("protrudes") else 0.0
    mi = next((k for k, e in enumerate(elems) if e["kind"] == "middle"), None)
    seats_left = sum(e["len"] for e in elems[:mi]) if mi is not None else 0.0
    seats_right = sum(e["len"] for e in elems[mi + 1:]) if mi is not None else 0.0
    # the axle's journals: right through the bearings and beyond on a long axle, half-way into them on a short one
    journal = lambda seats: seats + protrusion if protrusion else seats / 2
    free = None
    if removing:
        part_left = x - left_len if inside else x + (journal(seats_left) - seats_left if axle_in else 0.0)
    else:
        free = (x, x + d["width"])
        _bearing(c, x, d)
        part_left = free[1] + 3

    # ---- the part itself: one body, its bore stepping from seat to seat, with what is still in it
    segments, px = [], part_left
    for k, e in enumerate(elems):
        e["x0"], e["x1"] = px, px + e["len"]
        if e["kind"] == "seat":
            segments.append((e["x0"], e["x1"], e["dims"]["outer"] / 2))
            if e["present"] and not (e.get("worked") and not removing):
                _bearing(c, e["x0"], e["dims"])
        else:
            around = [n["dims"]["outer"] for n in elems[max(k - 1, 0):k + 2] if n["kind"] == "seat"] or [d["outer"]]
            segments.append((e["x0"], e["x1"], min(around) / 2 - 3))
            if e["what"] == "spacer":
                # with the ALT Drift, the spacer is pushed off its axis so that the drift can get past it
                c.ring(e["x0"], e["len"], d["inner"] / 2, d["inner"] / 2 + 2, SPACER, shift=1.5 if alt_drift_job else 0)
        px = e["x1"]
    part_right = px
    _part(c, segments, part_r)
    worked = elems[wi]
    middle = next((e for e in elems if e["kind"] == "middle"), None)

    axle = None
    if axle_in and middle:
        # a stepped cylinder: a body between the bearings whose shoulders touch their inner rings, and a thinner
        # journal on each side that the bearings sit on; hollow, so the pilots can centre in its ends
        bore = max(d["inner"] / 2 - 3, STUD_R + 0.5)
        journal_r = d["inner"] / 2
        body_r = min(journal_r + 2.5, segments[mi][2] - 0.8)
        a0 = free[0] - 18 if (free and protrusion) else middle["x0"] - journal(seats_left)
        a1 = middle["x1"] + journal(seats_right)
        axle = (a0, a1)
        c.profile([(a0, bore), (a0, journal_r), (middle["x0"], journal_r), (middle["x0"], body_r),
                   (middle["x1"], body_r), (middle["x1"], journal_r), (a1, journal_r), (a1, bore)], AXLE)

    # ---- spans of the things the stack names, for the labels and for the pilots that sit inside them
    others = [e for e in elems if e["kind"] == "seat" and not e.get("worked")]
    nearest = min((e for e in others if e["present"]), key=lambda e: abs(e["x0"] - worked["x0"]), default=None) \
        or (others[0] if others else worked)
    spans = {}
    for i in work:
        token = stack[i]["piece"]
        if token in ("bearing", "bearing_in_part"):
            x0, x1 = free if free else (worked["x0"], worked["x1"])
            spans[i] = (x0, x1, d)
            c.label((x0 + x1) / 2, d["outer"] / 2, i, above=False)
        elif token == "other_bearing":
            spans[i] = (nearest["x0"], nearest["x1"], nearest["dims"])
            c.label((nearest["x0"] + nearest["x1"]) / 2, nearest["dims"]["outer"] / 2, i, above=False)
        elif token == "axle" and axle:
            spans[i] = (axle[0], axle[1], d)
            mid = middle or worked
            c.label((mid["x0"] + mid["x1"]) / 2, min(d["inner"] / 2 + 2.5, segments[mi][2] - 0.8), i, above=False)
        elif token in ("spacer", "axle") and middle:
            spans[i] = (middle["x0"], middle["x1"], d)
            c.label((middle["x0"] + middle["x1"]) / 2, d["inner"] / 2 + 2 + (1.5 if alt_drift_job else 0), i, above=False)
        else:                          # "part" or "bore": point at the body of the part
            mid = middle or worked
            c.label((mid["x0"] + mid["x1"]) / 2, part_r, i, above=False)

    # ---- pieces that work from inside the part
    stud_from: Optional[float] = 2.0
    for i, item in enumerate(stack):
        if item["piece"] == "alt_drift":
            head = worked["x0"] - LEN["alt_drift"]
            top = _size(item, d["inner"]) / 2 + 1.2
            if state["rod_from"] is not None:
                c.ring(state["rod_from"], head - state["rod_from"], 0, 5.5, ALUMINIUM)
            c.ring(head, LEN["alt_drift"], 0, top, ALUMINIUM)
            stud_from = head + 2           # the Stud threads into the drift from the other side
            c.label(head + LEN["alt_drift"] / 2, top, i, above=True, resolved=item["resolved"])
        elif item["piece"] == "alt_extractor":
            # as in the tool: a wedge behind the bearing, the collet inside it with its retaining ring, the grooved
            # body in front, and a threaded rod pointing out through the sleeve
            r = _size(item, d["inner"]) / 2
            top = min(r + 3.5, d["outer"] / 2 - 1.5)
            c.ring(worked["x0"] - 9, 9, 0, r - 0.4, ALUMINIUM)
            c.ring(worked["x0"], d["width"], 0, r, ALUMINIUM)
            c.ring(worked["x0"] + d["width"] / 2 - 0.5, 1, r - 1.4, r, ACETAL)
            c.ring(worked["x1"], 14, 0, top, ALUMINIUM)
            c.lines(worked["x1"], 14, top, 4)
            stud_from = worked["x1"] + 14
            # the bolt that expands the collet is in the head: with other bearings behind it, the key goes in
            # the other way round, long arm first, through the part
            if left_len:
                c.long_key(worked["x0"] - 7, part_left - 8)
            else:
                c.allen_key(worked["x0"] - 9, outward=-1)
            c.label(worked["x1"] + 7, top, i, above=True, resolved=item["resolved"])

    # ---- pieces after the part
    x = part_right
    for i in after:
        x = draw(i, x, "after")

    # ---- pilots, inside what they centre, each with the O-ring that keeps it from sliding
    for i, item in enumerate(stack):
        if not (item["piece"] in ("pilot_short", "pilot_long") and item["role"] == "center"):
            continue
        nxt = stack[i + 1]["piece"] if i + 1 < len(stack) else None
        prev = stack[i - 1]["piece"] if i > 0 else None
        # a pilot listed next to the axle goes inside the axle's end, even when a bearing is its other neighbour
        if "axle" in (nxt, prev) and axle:
            host = i + 1 if nxt == "axle" else i - 1
        else:
            host = i + 1 if nxt in HOSTS else next((j for j in range(i - 1, -1, -1) if stack[j]["piece"] in HOSTS), None)
        if host is None or host not in spans:
            continue
        h_start, h_end, dims = spans[host]
        # a pilot longer than its bearing reaches inwards, through the bearing and into the spacer behind it
        to_left = bool(middle) and (h_start + h_end) / 2 > (middle["x0"] + middle["x1"]) / 2
        length = LEN["pilot_long"] if item["piece"] == "pilot_long" else min(LEN["pilot_short"], h_end - h_start)
        r = _size(item, dims["inner"]) / 2
        if stack[host]["piece"] == "axle" and axle:      # a pilot sits in the end of the axle it is listed next to
            r = max(d["inner"] / 2 - 3, STUD_R + 0.5)
            px = h_start if i < host else h_end - length
            free_end = px + length if i < host else px
        else:
            px = h_end - length if to_left else h_start
            free_end = px if to_left else px + length
        c.ring(px, length, STUD_R, r, _colour(item, material))
        c.o_ring(free_end + (-0.9 if free_end == px else 0.9))
        c.label(px + length / 2, r, i, above=False, resolved=item["resolved"])

    total = x + 6
    has_rod = stud_from is not None and bool(pieces & {"handle", "stud_stop", "nut"})
    rod = _thread(stud_from, total - 2) if has_rod else ""
    moving = ((free[0] + free[1]) / 2, d["outer"] / 2) if free else ((worked["x0"] + worked["x1"]) / 2, part_r)

    # letter badges in one row above (pieces) and one below (the workpiece and the pilots inside it), spread out
    # so that no two touch; each has a straight leader ending in a dot on the thing it names
    body = c.max_r * PX + 26
    above = sorted(l for l in c.labels if l[1] < 0)
    below = sorted(l for l in c.labels if l[1] >= 0)
    width = max(total * PX, max(len(above), len(below)) * BADGE_GAP + 8)
    row = BADGE_R + 6
    top_edge, bottom_edge = body + 2 * row, body + 2 * row

    # everything was laid out with the bearing travelling to the right; when that shows the part from behind,
    # the picture is mirrored, so that the part stays put and the tool changes sides
    mirrored = _mirrored(scene, removing)
    flip = (lambda px: total * PX - px) if mirrored else (lambda px: px)
    above = sorted((flip(tx), ty, letter, open_) for tx, ty, letter, open_ in above)
    below = sorted((flip(tx), ty, letter, open_) for tx, ty, letter, open_ in below)

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 {-top_edge:.0f} {width:.0f} {top_edge + bottom_edge:.0f}" '
           f'width="{width:.0f}" height="{top_edge + bottom_edge:.0f}" font-family="Helvetica, Arial, sans-serif">',
           f'<rect x="0" y="{-top_edge:.0f}" width="{width:.0f}" height="{top_edge + bottom_edge:.0f}" fill="#ffffff"/>',
           f'<g transform="translate({total * PX:.1f},0) scale(-1,1)">' if mirrored else '<g>',
           rod] + c.shapes + ['</g>']
    for tx, ty in c.marks:
        out.append(_turn_sign(flip(tx), ty - 9))

    # which way the bearing travels
    mx, mr, way = flip(moving[0] * PX), -(moving[1] + 3) * PX, -1 if mirrored else 1
    tip = mx + way * 28
    out.append(f'<line x1="{mx - way * 16:.1f}" y1="{mr:.1f}" x2="{tip - way * 12:.1f}" y2="{mr:.1f}" stroke="{MOVE}" stroke-width="3"/>'
               f'<polygon points="{tip:.1f},{mr:.1f} {tip - way * 20:.1f},{mr - 9:.1f} {tip - way * 20:.1f},{mr + 9:.1f}" fill="{MOVE}"/>')

    for group, side in ((above, -1), (below, 1)):
        xs = _spread([l[0] for l in group], BADGE_R + 4, width - BADGE_R - 4)
        cy = side * (body + row)
        for (tx, ty, letter, open_), bx in zip(group, xs):
            edge = cy - side * BADGE_R
            for stroke, w in (("#ffffff", 3.5), (LINE, 1.2)):      # a white halo keeps the leader visible on black
                out.append(f'<line x1="{bx:.1f}" y1="{edge:.1f}" x2="{tx:.1f}" y2="{ty:.1f}" stroke="{stroke}" stroke-width="{w}"/>')
            out.append(f'<circle cx="{tx:.1f}" cy="{ty:.1f}" r="2.6" fill="{LINE}" stroke="#ffffff" stroke-width="1"/>')
            # a piece whose size is still to be chosen gets an amber badge
            out.append(f'<circle cx="{bx:.1f}" cy="{cy:.1f}" r="{BADGE_R}" fill="{"#fcd34d" if open_ else "#ffffff"}" '
                       f'stroke="{LINE}" stroke-width="1.2"/>')
            out.append(f'<text x="{bx:.1f}" y="{cy + 5.5:.1f}" font-family="Helvetica, Arial, sans-serif" '
                       f'font-size="16" font-weight="bold" text-anchor="middle" '
                       f'fill="{LINE}">{letter}</text>')
    out.append("</svg>")
    return "\n".join(out)
