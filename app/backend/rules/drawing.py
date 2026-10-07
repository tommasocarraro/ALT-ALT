"""
Draws one job of the rule engine as a section view: the pieces in a row on the Stud, cut through the middle,
in the order the engine's `stack` gives them.

Diameters are to scale (they come from the bearing and from the piece sizes); lengths are only indicative,
because the real lengths of the pieces are not in the catalogue.
Pieces are coloured by what they are made of: acetal black, aluminium gold, steel grey.
Each piece carries the letter it has in the written instructions (a, b, c, ... in stack order), so the drawing
needs no text of its own.
"""
from typing import List, Optional, Tuple

PX = 4.0            # pixels per millimetre
STUD_R = 4.0        # M8 stud
DEFAULT = {"inner": 15.0, "outer": 28.0, "width": 7.0}     # drawn when a bearing's dimensions are unknown

# indicative lengths, in millimetres
LEN = {"drift_re": 16, "sleeve": 30, "sleeve_6": 30, "sleeve_long": 36, "oa_drift": 44, "spacer_tube": 45,
       "pilot_short": 6, "pilot_long": 18, "handle": 24, "stud_stop": 5, "stop_ctr": 16, "alt_drift": 8,
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

    def dots(self, x: float, r: float) -> None:
        """An O-ring on the Stud, cut through: a black dot above and below."""
        for s in (-1, 1):
            self.shapes.append(f'<circle cx="{x * PX:.1f}" cy="{s * r * PX:.1f}" r="{1.0 * PX:.1f}" fill="#111827"/>')

    def allen_key(self, x: float, outward: int) -> None:
        """An L-shaped key in the end of a piece; `outward` is -1 when the end faces left, +1 when it faces right."""
        tip, corner = (x - outward * 7) * PX, (x + outward * 7) * PX
        self.shapes.append(f'<path d="M{tip:.1f},0 L{corner:.1f},0 L{corner:.1f},{-24 * PX:.1f}" fill="none" '
                           f'stroke="{DARK_STEEL}" stroke-width="{1.6 * PX:.1f}" stroke-linejoin="round" stroke-linecap="round"/>')
        self.max_r = max(self.max_r, 25)
        self.turn(x + outward * 7, 25)

    def turn(self, x: float, r: float) -> None:
        """Marks the piece that is turned."""
        self.shapes.append(f'<text x="{x * PX:.1f}" y="{-(r + 1.5) * PX:.1f}" font-size="26" font-weight="bold" '
                           f'text-anchor="middle" fill="{MOVE}">↻</text>')
        self.max_r = max(self.max_r, r + 8)

    def label(self, x: float, r: float, index: int, above: bool, resolved: bool = True) -> None:
        """A letter pointing at the surface of something, at radius r above or below the axis."""
        self.labels.append((x * PX, (-r if above else r) * PX, chr(97 + index), not resolved))


def _thread(x1: float, x2: float) -> str:
    """The Stud, hatched like a thread."""
    box = f'x="{x1 * PX:.1f}" y="{-STUD_R * PX:.1f}" width="{(x2 - x1) * PX:.1f}" height="{2 * STUD_R * PX:.1f}"'
    return (f'<rect {box} fill="#d9d2ca" stroke="{LINE}" stroke-width="0.8"/>'
            f'<rect {box} fill="url(#thread)"/>')


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
        return DARK_STEEL
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


def svg_for(job: dict) -> str:
    """The job as a standalone SVG image."""
    d = job.get("bearing_dimensions") or DEFAULT
    other = job.get("other_dimensions") or d
    material = job.get("material") or "Aluminum"
    stack = job["stack"]
    pieces = {item["piece"] for item in stack}
    alt_drift_job = "alt_drift" in pieces
    c = _Canvas()
    # room on the left for the Allen key in the ALT Rod, or for the ALT Extractor's head behind the bearing
    x = 18.0 if alt_drift_job else 28.0 if "alt_extractor" in pieces else 6.0
    sleeve_inner, sleeve_outer = d["outer"] / 2 + 0.5, d["outer"] / 2 + 3.5
    part_r = max(d["outer"], other["outer"]) / 2 + 7
    part: List[Tuple[float, float, float]] = []      # the bore of the bike part: (from, to, radius)
    spans = {}            # stack index -> (x start, x end, bearing dims) of the things pilots can sit in
    pilots = []           # (stack index of the pilot, stack index of its host, extends to the left?)
    stud_from: Optional[float] = 2.0      # where the threaded rod starts; None when the job has none
    rod_from: Optional[float] = None      # start of the ALT Rod, drawn once the ALT Drift's place is known
    moving = None         # (x, radius) of the bearing that the job moves
    seen_workpiece = False

    # where does each centring pilot sit? inside the next bearing or axle, or else inside the previous one
    for i, item in enumerate(stack):
        if item["piece"] in ("pilot_short", "pilot_long") and item["role"] == "center":
            nxt = stack[i + 1]["piece"] if i + 1 < len(stack) else None
            host = i + 1 if nxt in HOSTS else next((j for j in range(i - 1, -1, -1) if stack[j]["piece"] in HOSTS), None)
            if host is not None:
                inward_left = host > 0 and stack[host - 1]["kind"] == "workpiece" and host > i
                pilots.append((i, host, inward_left if host > i else True))

    for i, item in enumerate(stack):
        piece = item["piece"]
        colour = _colour(item, material)
        start = x

        if item["kind"] == "workpiece":
            seen_workpiece = True
            dims = other if piece == "other_bearing" else d
            r_out = dims["outer"] / 2
            target_r = r_out
            if piece in ("bearing", "bearing_in_part", "other_bearing"):
                x += _bearing(c, x, dims)
                if piece != "bearing":
                    part.append((start, x, r_out))
                if piece != "other_bearing":
                    moving = ((start + x) / 2, part_r if piece == "bearing_in_part" else r_out)
                if piece == "bearing":
                    x += 3            # a new bearing is drawn just outside its seat
                label_x = start + dims["width"] / 2
            elif piece == "spacer":
                # with the ALT Drift, the spacer is pushed off its axis so that the drift can get past it
                c.ring(x, LEN["spacer"], dims["inner"] / 2, dims["inner"] / 2 + 2, SPACER, shift=1.5 if alt_drift_job else 0)
                x += LEN["spacer"]
                part.append((start, x, r_out - 3))
                target_r, label_x = dims["inner"] / 2 + 2 + (1.5 if alt_drift_job else 0), (start + x) / 2
            elif piece == "axle":
                c.ring(x - 6, LEN["axle"] + 12, max(dims["inner"] / 2 - 3, STUD_R + 0.5), dims["inner"] / 2, AXLE)
                x += LEN["axle"]
                part.append((start, x, r_out - 3))
                target_r, label_x = dims["inner"] / 2, (start + x) / 2
            else:                     # "part" or "bore": an empty seat, then the body of the part
                x += dims["width"] + LEN["body"]
                part += [(start, start + dims["width"], r_out), (start + dims["width"], x, r_out - 3)]
                target_r, label_x = part_r, start + dims["width"] + LEN["body"] / 2
            spans[i] = (start, x, dims)
            c.label(label_x, target_r, i, above=False)
            continue

        if piece in ("pilot_short", "pilot_long") and item["role"] == "center":
            continue                  # drawn afterwards, inside its bearing or axle
        top = 6.5
        if piece == "nut":
            c.ring(x, 6, STUD_R, 6.5, colour); x += 6
        elif piece == "handle":
            top = 10
            c.ring(x, LEN["handle"], 0, top, colour)
            c.lines(x + 6, LEN["handle"] - 8, top, 7)
            x += LEN["handle"]
            c.turn(start + 5, top)          # beside the label's leader, not on it
        elif piece == "stud_stop":
            top = 9
            c.ring(x, LEN["stud_stop"], STUD_R, top, colour); x += LEN["stud_stop"]
        elif piece == "drift_re":
            top = _size(item, d["outer"]) / 2
            # pressing: flat face on the bearing, recess away from it; leveraging: recess towards the part,
            # which is where the bearing and the pilot need the room
            relief = "left" if item["role"] == "leverage" or not seen_workpiece else "right"
            if "relief side towards the bearing" in (item.get("text") or ""):
                relief = "right"
            _drift(c, x, top, colour, relief); x += LEN["drift_re"]
        elif piece == "pilot_short":      # used as a pressing piece on the end of an axle
            top = _size(item, d["inner"]) / 2
            c.ring(x, 8, STUD_R, top, colour); x += 8
        elif piece in ("sleeve", "sleeve_6", "sleeve_long"):
            sleeve_inner = {"sleeve": _size(item, d["outer"]) / 2 + 0.5, "sleeve_6": 19.0, "sleeve_long": 18.0}[piece]
            top = sleeve_outer = sleeve_inner + (3 if piece == "sleeve" else 5)
            c.ring(x, LEN[piece], sleeve_inner, sleeve_outer, colour); x += LEN[piece]
        elif piece == "step":
            top = sleeve_outer + 6
            x += _step(c, x, sleeve_inner, sleeve_outer, colour)
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
            # the rod runs through the far bearing and the spacer; only its outer end is drawn here
            top, rod_from = 5.5, x
            c.allen_key(x, outward=-1)
            x += 14
        elif piece == "alt_drift":
            top = _size(item, d["inner"]) / 2 + 1.2
            if rod_from is not None:
                c.ring(rod_from, x - rod_from, 0, 5.5, _colour({"piece": "alt_rod"}, material))
            c.ring(x, LEN["alt_drift"], 0, top, colour)
            part.append((x, x + LEN["alt_drift"], d["outer"] / 2 - 3))
            stud_from = x + 2          # the Stud threads into the drift from the other side
            x += LEN["alt_drift"]
        elif piece == "alt_extractor":
            # as in the tool: a wedge behind the bearing, the collet inside it with its retaining ring, the grooved
            # body in front, and a threaded rod pointing out through the sleeve. It adds no length to the row.
            r = _size(item, d["inner"]) / 2
            b_start = x - d["width"]
            top = min(r + 3.5, d["outer"] / 2 - 1.5)
            c.ring(b_start - 9, 9, 0, r - 0.4, colour)
            c.allen_key(b_start - 9, outward=-1)        # the bolt that expands the collet is in the head
            c.ring(b_start, d["width"], 0, r, colour)
            c.ring(b_start + d["width"] / 2 - 0.5, 1, r - 1.4, r, ACETAL)
            c.ring(x, 14, 0, top, colour)
            c.lines(x, 14, top, 4)
            stud_from = x + 14
            c.label(x + 7, top, i, above=True, resolved=item["resolved"])
            continue
        elif piece == "oa_drift":
            try:
                inner, top = (float(v) / 2 for v in str(item["size"]).split("x"))
            except ValueError:
                inner, top = d["inner"] / 2, d["outer"] / 2
            c.ring(x, LEN["oa_drift"], inner, top, colour); x += LEN["oa_drift"]
        else:
            top = 8
            c.ring(x, 8, STUD_R, top, STEEL); x += 8
        label_x = start + 7 if piece == "alt_rod" else (start + x) / 2
        c.label(label_x, top, i, above=True, resolved=item["resolved"])

    _part(c, part, part_r)

    # pilots, inside what they centre, each with the O-ring that keeps it from sliding
    for i, host, to_left in pilots:
        if host not in spans:
            continue
        item = stack[i]
        h_start, h_end, dims = spans[host]
        is_axle = stack[host]["piece"] == "axle"
        host_len = dims["width"] if not is_axle else h_end - h_start
        length = LEN["pilot_long"] if item["piece"] == "pilot_long" else min(LEN["pilot_short"], host_len)
        r = _size(item, dims["inner"]) / 2
        if is_axle:                    # a pilot sits in the end of the axle it is listed next to
            r = max(dims["inner"] / 2 - 3, STUD_R + 0.5)
            px = h_start - 4 if i < host else h_end + 4 - length
            free_end = px + length if i < host else px
        else:
            px = h_start + host_len - length if to_left else h_start
            free_end = px if to_left else px + length
        c.ring(px, length, STUD_R, r, _colour(item, material))
        c.dots(free_end + (-1.1 if free_end == px else 1.1), STUD_R + 1.0)
        c.label(px + length / 2, r, i, above=False, resolved=item["resolved"])

    total = x + 6
    has_rod = stud_from is not None and ("handle" in pieces or "stud_stop" in pieces or "nut" in pieces)
    rod = _thread(stud_from, total - 2) if has_rod else ""

    # letter badges in one row above (pieces) and one below (the workpiece and the pilots inside it), spread out
    # so that no two touch; each has a straight leader ending in a dot on the thing it names
    body = c.max_r * PX + 26
    above = sorted(l for l in c.labels if l[1] < 0)
    below = sorted(l for l in c.labels if l[1] >= 0)
    width = max(total * PX, max(len(above), len(below)) * BADGE_GAP + 8)
    row = BADGE_R + 6
    top_edge, bottom_edge = body + 2 * row, body + 2 * row

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 {-top_edge:.0f} {width:.0f} {top_edge + bottom_edge:.0f}" '
           f'width="{width:.0f}" height="{top_edge + bottom_edge:.0f}" font-family="Helvetica, Arial, sans-serif">',
           '<defs><pattern id="thread" width="5" height="32" patternUnits="userSpaceOnUse" '
           f'y="{-STUD_R * PX:.0f}"><path d="M0,{2 * STUD_R * PX:.0f} L5,0" stroke="#6b7280" stroke-width="1.1"/></pattern>'
           f'<marker id="head" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">'
           f'<path d="M0,0 L8,4 L0,8 z" fill="{MOVE}"/></marker></defs>',
           f'<rect x="0" y="{-top_edge:.0f}" width="{width:.0f}" height="{top_edge + bottom_edge:.0f}" fill="#ffffff"/>',
           rod] + c.shapes

    if moving:                         # which way the bearing travels: always towards the leverage end
        mx, mr = moving[0] * PX, -(moving[1] + 3) * PX
        out.append(f'<line x1="{mx - 16:.1f}" y1="{mr:.1f}" x2="{mx + 22:.1f}" y2="{mr:.1f}" stroke="{MOVE}" '
                   f'stroke-width="3" marker-end="url(#head)"/>')

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
            out.append(f'<text x="{bx:.1f}" y="{cy + 5.5:.1f}" font-size="16" font-weight="bold" text-anchor="middle" '
                       f'fill="{LINE}">{letter}</text>')
    out.append("</svg>")
    return "\n".join(out)
