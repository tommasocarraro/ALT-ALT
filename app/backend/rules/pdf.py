"""
The instructions of a whole project as a PDF: for every arrangement, each job with its title (arrangement, job and
bearing), its section drawing and its lettered steps, one job after the other. A coloured line separates the
arrangements.

Laid out by hand with PyMuPDF, which the app already uses, so nothing else has to be installed. The drawings are
the SVGs of drawing.py, placed as vector graphics.
"""
import datetime
from typing import Callable, List, Optional, Tuple

import pymupdf

from app.backend.rules.drawing import svg_for

W, H = pymupdf.paper_size("a4")
MARGIN, TOP, BOTTOM = 42.0, 46.0, H - 52.0
CONTENT = W - 2 * MARGIN


def _rgb(colour: str) -> Tuple[float, float, float]:
    return tuple(int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5))


INK, MUTED, FAINT, RULE = _rgb("#0f172a"), _rgb("#64748b"), _rgb("#94a3b8"), _rgb("#e2e8f0")
ACCENT, TINT, WHITE = _rgb("#d6249f"), _rgb("#f8fafc"), (1.0, 1.0, 1.0)
AMBER, AMBER_FILL, ACCENT_TINT = _rgb("#b45309"), _rgb("#fcd34d"), _rgb("#fdf2f8")
# the colours of the drawings, for the legend
LEGEND = [("Acetal", "#262626"), ("Aluminium", "#e0b021"), ("Steel", "#9aa0a6"), ("Bike part", "#b6c0da")]

REGULAR, BOLD, ITALIC = pymupdf.Font("helv"), pymupdf.Font("hebo"), pymupdf.Font("heit")
Run = Tuple[str, pymupdf.Font]
Block = Tuple[float, Callable[["_Sheet", float], None]]      # height, and how to draw it with its top at y


class _Sheet:
    """The document being written: the current page, how far down it is filled, and the text waiting to go on it."""

    def __init__(self) -> None:
        self.doc = pymupdf.open()
        self.page: Optional[pymupdf.Page] = None
        self.writers: dict = {}
        self.y = TOP
        self.new_page()

    def new_page(self) -> None:
        self.flush()
        self.page = self.doc.new_page(width=W, height=H)
        self.y = TOP

    def flush(self) -> None:
        """Text is written last, so that it always lies on top of the boxes behind it."""
        for writer in self.writers.values():
            writer.write_text(self.page)
        self.writers = {}

    def text(self, x: float, baseline: float, s: str, font: pymupdf.Font = REGULAR, size: float = 9.5,
             colour: Tuple[float, float, float] = INK) -> None:
        writer = self.writers.get(colour)
        if writer is None:
            writer = self.writers[colour] = pymupdf.TextWriter(self.page.rect, color=colour)
        writer.append((x, baseline), s, font=font, fontsize=size)

    def room(self, height: float) -> None:
        """Starts a new page when the next `height` points do not fit on this one."""
        if self.y + height > BOTTOM and self.y > TOP:
            self.new_page()

    def put(self, blocks: List[Block], keep: int = 0) -> None:
        """Draws the blocks one under the other; together on one page if they fit, else at least the first `keep`."""
        total = sum(h for h, _ in blocks)
        self.room(total if total <= BOTTOM - TOP else sum(h for h, _ in blocks[:keep]))
        for height, draw in blocks:
            self.room(height)
            draw(self, self.y)
            self.y += height


def _wrap(runs: List[Run], size: float, width: float) -> List[List[Tuple[str, pymupdf.Font, float]]]:
    """The runs broken into lines no wider than `width`: each line a list of (word, font, x offset)."""
    lines, line, used = [], [], 0.0
    for text, font in runs:
        for word in text.split():
            w = font.text_length(word, fontsize=size)
            # punctuation that opens a run sticks to the word before it
            gap = font.text_length(" ", fontsize=size) if line and word[0] not in ":,." else 0.0
            if line and used + gap + w > width:
                lines.append(line)
                line, used, gap = [], 0.0, 0.0
            line.append((word, font, used + gap))
            used += gap + w
    return lines + ([line] if line else [])


def _para(runs: List[Run], x: float, width: float, size: float = 9.5, colour=INK, after: float = 3.0,
          decorate: Optional[Callable[["_Sheet", float, float], None]] = None) -> Block:
    """A wrapped paragraph. `decorate(sheet, top, height)` draws what goes with it (a badge, a box behind it)."""
    lines, leading = _wrap(runs, size, width), size * 1.38
    height = len(lines) * leading + after

    def draw(sheet: _Sheet, y: float) -> None:
        if decorate:
            decorate(sheet, y, height - after)
        for k, line in enumerate(lines):
            for word, font, dx in line:
                sheet.text(x + dx, y + size + k * leading, word, font, size, colour)
    return height, draw


def _gap(height: float) -> Block:
    return height, lambda sheet, y: None


def _dims(d: Optional[dict]) -> str:
    if not d:
        return ""
    fmt = lambda v: "?" if v is None else str(int(v)) if float(v).is_integer() else str(v)
    return f"{fmt(d['inner'])} × {fmt(d['outer'])} × {fmt(d['width'])} mm"


# ---------------------------------------------------------------------------------------------------
# The parts of the document
# ---------------------------------------------------------------------------------------------------
def _cover(sheet: _Sheet, project: dict, results: List[dict]) -> None:
    """The band across the top of the first page, and the key to the drawings under it."""
    page, band = sheet.page, 118.0
    page.draw_rect(pymupdf.Rect(0, 0, W, band), color=None, fill=INK)
    page.draw_rect(pymupdf.Rect(0, band, W, band + 4), color=None, fill=ACCENT)
    sheet.text(MARGIN, 40, "ALT/ALT BEARING PRESS", BOLD, 8.5, _rgb("#f0abdc"))
    sheet.text(MARGIN, 40 + 13, "Removal and installation instructions", REGULAR, 8.5, FAINT)
    title = _wrap([(project.get("title") or "Instructions", BOLD)], 22, CONTENT)[:1]
    for word, font, dx in (title[0] if title else []):
        sheet.text(MARGIN + dx, 84, word, font, 22, WHITE)
    bike = " ".join(x for x in (project.get("manufacturer"), project.get("model")) if x)
    jobs = sum(len(r["jobs"]) for r in results)
    facts = [bike, f"{len(results)} arrangement{'s' if len(results) != 1 else ''}", f"{jobs} jobs",
             datetime.date.today().strftime("%d %B %Y").lstrip("0")]
    sheet.text(MARGIN, 103, "   ·   ".join(f for f in facts if f), REGULAR, 9, _rgb("#cbd5e1"))

    # key: what the colours, the amber badge and the arrow mean
    x, y = MARGIN, band + 24
    for name, colour in LEGEND:
        page.draw_rect(pymupdf.Rect(x, y - 7, x + 11, y + 1), color=INK, fill=_rgb(colour), width=0.4, radius=0.2)
        sheet.text(x + 15, y, name, REGULAR, 8, MUTED)
        x += 15 + REGULAR.text_length(name, fontsize=8) + 14
    page.draw_circle((x + 5, y - 3), 5, color=INK, fill=AMBER_FILL, width=0.5)
    sheet.text(x + 14, y, "size to choose with the part in hand", REGULAR, 8, MUTED)
    x += 14 + REGULAR.text_length("size to choose with the part in hand", fontsize=8) + 14
    page.draw_line((x, y - 3), (x + 12, y - 3), color=ACCENT, width=1.6)
    page.draw_polyline([(x + 18, y - 3), (x + 11, y - 6.2), (x + 11, y + 0.2)], color=None, fill=ACCENT, closePath=True)
    sheet.text(x + 23, y, "way the bearing travels", REGULAR, 8, MUTED)
    sheet.y = y + 24


def _arrangement_head(result: dict, first: bool) -> List[Block]:
    """The line that separates one arrangement from the one before, then its name, rule set and bearings."""
    blocks: List[Block] = []
    if not first:
        def line(sheet: _Sheet, y: float) -> None:
            sheet.page.draw_line((MARGIN, y + 12), (W - MARGIN, y + 12), color=ACCENT, width=1.6)
        blocks.append((30.0, line))
    blocks.append(_para([(result["arrangement"], BOLD)], MARGIN, CONTENT, 16, INK, after=2))
    codes = list(dict.fromkeys(j["bearing"] for j in result["jobs"] if j["bearing"]))
    sub = result["rule_set_name"] + (f"   ·   Bearings: {', '.join(codes)}" if codes else "")
    blocks.append(_para([(sub, REGULAR)], MARGIN, CONTENT, 9, MUTED, after=4))
    for a in result["assumptions"]:
        blocks.append(_para([("Assumed:", BOLD), (a, REGULAR)], MARGIN, CONTENT, 8.5, AMBER, after=2))
    blocks.append(_gap(8))
    return blocks


def _title(n: int, arrangement: str, job: dict) -> Block:
    """Number, arrangement name and job, with the bearing and its size in a chip on the right."""
    size, chip_size, pad = 11.5, 8.5, 6.0
    code, dims = job.get("bearing") or "", _dims(job.get("bearing_dimensions"))
    chip_w = 0.0
    if code:
        chip_w = BOLD.text_length(code, fontsize=chip_size) + 2 * pad
        chip_w += REGULAR.text_length(dims, fontsize=chip_size) + 8 if dims else 0
    left = MARGIN + 26
    width = CONTENT - 26 - (chip_w + 10 if chip_w else 0)
    # the arrangement goes first only if the job's own title does not already start a line of its own
    lines = _wrap([(arrangement, REGULAR), ("—", REGULAR), (job["title"], BOLD)], size, width)
    leading = size * 1.3
    height = max(len(lines) * leading, 20) + 8

    def draw(sheet: _Sheet, y: float) -> None:
        page = sheet.page
        page.draw_circle((MARGIN + 9, y + 9), 9, color=None, fill=ACCENT)
        label = str(n)
        sheet.text(MARGIN + 9 - BOLD.text_length(label, fontsize=10) / 2, y + 12.6, label, BOLD, 10, WHITE)
        for k, line in enumerate(lines):
            for word, font, dx in line:
                sheet.text(left + dx, y + 13 + k * leading, word, font, size, MUTED if font is REGULAR else INK)
        if code:
            x0 = W - MARGIN - chip_w
            page.draw_rect(pymupdf.Rect(x0, y + 1, W - MARGIN, y + 17), color=RULE, fill=TINT, width=0.6, radius=0.3)
            sheet.text(x0 + pad, y + 12, code, BOLD, chip_size, INK)
            if dims:
                sheet.text(x0 + pad + BOLD.text_length(code, fontsize=chip_size) + 8, y + 12, dims, REGULAR, chip_size, MUTED)
    return height, draw


def _diagram(job: dict) -> Block:
    """The section drawing, as vector graphics, centred in a frame."""
    picture = pymupdf.open("pdf", pymupdf.open(stream=svg_for(job).encode(), filetype="svg").convert_to_pdf())
    w, h = picture[0].rect.width, picture[0].rect.height
    scale = min((CONTENT - 16) / w, 205 / h, 0.6)
    w, h = w * scale, h * scale

    def draw(sheet: _Sheet, y: float) -> None:
        sheet.page.draw_rect(pymupdf.Rect(MARGIN, y, W - MARGIN, y + h + 12), color=RULE, fill=WHITE, width=0.7, radius=0.02)
        x0 = MARGIN + (CONTENT - w) / 2
        sheet.page.show_pdf_page(pymupdf.Rect(x0, y + 6, x0 + w, y + 6 + h), picture, 0)
    return h + 12 + 10, draw


def _step(index: int, item: dict) -> Block:
    """One thing on the Stud, with the letter it has in the drawing."""
    letter, open_ = chr(97 + index), not item["resolved"]
    if item["kind"] == "workpiece":
        runs, colour = [(item["name"], ITALIC)], MUTED
    else:
        runs = [(item["name"], BOLD)] + ([(": " + item["text"], REGULAR)] if item["text"] else [])
        colour = AMBER if open_ else INK

    def badge(sheet: _Sheet, y: float, height: float) -> None:
        sheet.page.draw_circle((MARGIN + 7, y + 6.4), 6.2, color=INK, fill=AMBER_FILL if open_ else WHITE, width=0.6)
        sheet.text(MARGIN + 7 - BOLD.text_length(letter, fontsize=8) / 2, y + 9.2, letter, BOLD, 8, INK)
    return _para(runs, MARGIN + 21, CONTENT - 21, 9.5, colour, after=3.2, decorate=badge)


def _action(text: str) -> Block:
    """What to do once everything is assembled, in a tinted box."""
    def box(sheet: _Sheet, y: float, height: float) -> None:
        sheet.page.draw_rect(pymupdf.Rect(MARGIN, y - 5, W - MARGIN, y + height + 5), color=None, fill=ACCENT_TINT)
        sheet.page.draw_rect(pymupdf.Rect(MARGIN, y - 5, MARGIN + 2.5, y + height + 5), color=None, fill=ACCENT)
        sheet.text(MARGIN + 11, y + 9.5, "THEN", BOLD, 7.5, ACCENT)
    return _para([(text, REGULAR)], MARGIN + 44, CONTENT - 54, 9.5, INK, after=10, decorate=box)


def _job(n: int, arrangement: str, job: dict) -> Tuple[List[Block], int]:
    """Title, drawing, steps, action and remarks of one job; and how many of these blocks must stay together."""
    uses_stud = any(l["piece"] == "stud" for l in job["pieces"])
    heading = "PUT THESE ON THE STUD IN THIS ORDER, FROM ONE END TO THE OTHER" if uses_stud else "ASSEMBLE IN THIS ORDER"
    blocks = [_title(n, arrangement, job), _diagram(job),
              _para([(heading, BOLD)], MARGIN, CONTENT, 7, FAINT, after=5)]
    blocks += [_step(k, item) for k, item in enumerate(job["stack"])]
    keep = min(len(blocks), 4)

    extra = []
    o_rings = sum(l["qty"] for l in job["pieces"] if l["piece"] == "o_ring")
    if o_rings:
        extra.append(f"Use {o_rings} O-ring{'s' if o_rings > 1 else ''} on the Stud to keep the "
                     f"pilot{'s' if o_rings > 1 else ''} from sliding.")
    if uses_stud:
        extra.append("Stud length: choose with the part in hand.")
    if extra:
        blocks.append(_para([(" ".join(extra), REGULAR)], MARGIN + 21, CONTENT - 21, 9, MUTED, after=4))
    blocks += [_gap(8), _action(job["action"])]

    small = lambda label, text: _para([(label, BOLD), (text, REGULAR)], MARGIN, CONTENT, 8, MUTED, after=2.5)
    blocks += [small("Alternative", "for the " + alt) for alt in job["alternatives"]]
    blocks += [small("Note", note) for note in job["notes"]]
    if job["status"] != "diagram":
        blocks.append(small("Source", "no official diagram for this job; confirmed by the tool's maker."))
    elif job["diagram"]:
        blocks.append(small("Official diagram", job["diagram"]))
    blocks.append(_gap(20))
    return blocks, keep


def _footers(sheet: _Sheet, project: dict) -> None:
    pages = sheet.doc.page_count
    for n, page in enumerate(sheet.doc, 1):
        writer = pymupdf.TextWriter(page.rect, color=FAINT)
        page.draw_line((MARGIN, H - 36), (W - MARGIN, H - 36), color=RULE, width=0.6)
        writer.append((MARGIN, H - 24), project.get("title") or "", font=REGULAR, fontsize=8)
        label = f"Page {n} of {pages}"
        writer.append((W - MARGIN - REGULAR.text_length(label, fontsize=8), H - 24), label, font=REGULAR, fontsize=8)
        writer.write_text(page)


def pdf_for(project: dict, results: List[dict]) -> bytes:
    """
    The instructions of every arrangement of a project, with the drawings.

    :param project: {"title", "manufacturer", "model"}
    :param results: what `tools_for_project` returns
    """
    sheet = _Sheet()
    _cover(sheet, project, results)
    if not results:
        sheet.put([_para([("No arrangement has been described for this project yet.", REGULAR)], MARGIN, CONTENT, 10, MUTED)])
    for a, result in enumerate(results):
        head = _arrangement_head(result, first=a == 0)
        for n, job in enumerate(result["jobs"], 1):
            blocks, keep = _job(n, result["arrangement"], job)
            if n == 1:          # the name of the arrangement never stays alone at the foot of a page
                blocks, keep = head + blocks, len(head) + keep
            sheet.put(blocks, keep)
        if not result["jobs"]:
            sheet.put(head)
    sheet.flush()
    _footers(sheet, project)
    sheet.doc.set_metadata({"title": f"{project.get('title') or 'Project'}: bearing press instructions",
                            "creator": "ALT/ALT press planner"})
    return sheet.doc.tobytes(deflate=True, garbage=4)
