import hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, HttpUrl
import json
from sqlalchemy import (
    create_engine, Column, Integer, Text, Numeric, ForeignKey,
    UniqueConstraint, event, Enum as SAEnum, Boolean, text
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, Mapped, mapped_column, Session
from sqlalchemy.exc import IntegrityError
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.backend.llm.logic import from_url_to_bearings
from app.backend.utils import highlight_pdf
from app.backend.rules.engine import (
    ArrangementSpec, BearingSpec, tools_for, cart_for, instructions_for, apply_cart_edits, catalog_items, BY_SKU,
)
from app.backend.rules.drawing import svg_for
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

# -----------------------------
# Config
# -----------------------------
DB_PATH = "./app/backend/data/db"
DATABASE_URL = f"sqlite:///{DB_PATH}"
DIAGRAMS_DIR = Path("app/backend/data/diagrams")
DIAGRAMS_DIR.mkdir(parents=True, exist_ok=True)

# -----------------------------
# SQLAlchemy setup
# -----------------------------
engine = create_engine(DATABASE_URL, future=True, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, class_=Session, future=True)
Base = declarative_base()

# Ensure SQLite enforces FKs
@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, _):
    cur = dbapi_connection.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()

# ---------- Enums ----------
material_t = SAEnum("carbon", "alloy", name="material_t", native_enum=False)
arrangement_type_t = SAEnum("SP", "BSB", "OA", name="arrangement_type_t", native_enum=False)
oa_axle_length_t = SAEnum("short", "long", name="oa_axle_length_t", native_enum=False)
spacer_mobility_t = SAEnum("moves", "stuck", name="spacer_mobility_t", native_enum=False)
component_t = SAEnum("frame", "hub", "freehub", name="component_t", native_enum=False)
freehub_body_t = SAEnum("hg_microspline", "xd_xdr", name="freehub_body_t", native_enum=False)
# where a bearing code was read: printed in the diagram, or looked up on the web from a part reference
found_in_t = SAEnum("diagram", "web", name="found_in_t", native_enum=False)
# where a bearing's dimensions come from: the standard size table, the size spelled in the code, or a web page
dimensions_source_t = SAEnum("standard", "code", "web", name="dimensions_source_t", native_enum=False)

# number of bearing positions per arrangement type: a simple pivot has one seat, the others have one at each end
SLOTS_BY_TYPE = {"SP": 1, "BSB": 2, "OA": 2}

# -----------------------------
# ORM models - these are the models that represent the tables of the database
# -----------------------------
class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    diagram_url: Mapped[str] = mapped_column(Text, nullable=False)
    diagram_pdf_path: Mapped[str] = mapped_column(Text, nullable=False)
    manufacturer: Mapped[Optional[str]] = mapped_column(Text)
    model: Mapped[Optional[str]] = mapped_column(Text)
    # JSON list produced by the diagram analysis: bearings that could not be identified
    unresolved_references: Mapped[Optional[str]] = mapped_column(Text)

    # this is like the opposite of a foreign key. This means this table has a relationship with the table ProjectBearing
    bearings: Mapped[List["ProjectBearing"]] = relationship(
        "ProjectBearing", back_populates="project", cascade="all, delete-orphan"
    )


class Bearing(Base):
    __tablename__ = "bearings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    # dimensions stay empty when no source states them; a person fills them in
    inner_diameter: Mapped[Optional[float]] = mapped_column(Numeric(6, 2))
    outer_diameter: Mapped[Optional[float]] = mapped_column(Numeric(6, 2))
    width: Mapped[Optional[float]] = mapped_column(Numeric(6, 2))
    dimensions_source: Mapped[Optional[str]] = mapped_column(dimensions_source_t)
    dimensions_source_url: Mapped[Optional[str]] = mapped_column(Text)
    # optional fields
    extended_inner_ring_width: Mapped[Optional[float]] = mapped_column(Numeric(6, 2))
    flange_diameter: Mapped[Optional[float]] = mapped_column(Numeric(6, 2))

    # again, this means this table has a relationship with the ProjectBearing table
    projects: Mapped[List["ProjectBearing"]] = relationship("ProjectBearing", back_populates="bearing")


class ProjectBearing(Base):
    __tablename__ = "project_bearings"
    __table_args__ = (
        UniqueConstraint("project_id", "bearing_id", name="uq_project_bearing"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    bearing_id: Mapped[int] = mapped_column(ForeignKey("bearings.id", ondelete="RESTRICT"), nullable=False)
    quantity: Mapped[Optional[int]] = mapped_column(Integer)
    found_in: Mapped[str] = mapped_column(found_in_t, nullable=False, default="diagram")
    # callout label in the diagram, or the part number the code was looked up from
    reference: Mapped[Optional[str]] = mapped_column(Text)
    source_url: Mapped[Optional[str]] = mapped_column(Text)

    project: Mapped[Project] = relationship("Project", back_populates="bearings")
    bearing: Mapped[Bearing] = relationship("Bearing", back_populates="projects")


class Arrangement(Base):
    __tablename__ = "arrangements"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    material: Mapped[str] = mapped_column(material_t, nullable=False)
    type: Mapped[str] = mapped_column(arrangement_type_t, nullable=False)
    component: Mapped[str] = mapped_column(component_t, nullable=False, default="frame")
    # only for hubs
    has_center_lock: Mapped[bool | None] = mapped_column(Boolean)
    # only for freehubs
    freehub_body: Mapped[str | None] = mapped_column(freehub_body_t)
    freehub_one_side: Mapped[bool | None] = mapped_column(Boolean)

class ArrangementBSB(Base):
    __tablename__ = "arrangement_bsb"
    arrangement_id: Mapped[int] = mapped_column(ForeignKey("arrangements.id", ondelete="CASCADE"), primary_key=True)
    has_spacer: Mapped[bool] = mapped_column(Boolean, nullable=False)
    spacer_len_ge_10mm: Mapped[bool | None] = mapped_column(Boolean)
    spacer_mobility: Mapped[str | None] = mapped_column(spacer_mobility_t)

class ArrangementOA(Base):
    __tablename__ = "arrangement_over_axle"
    arrangement_id: Mapped[int] = mapped_column(ForeignKey("arrangements.id", ondelete="CASCADE"), primary_key=True)
    axle_length: Mapped[str] = mapped_column(oa_axle_length_t, nullable=False)

class ArrangementBearing(Base):
    """
    One bearing at one position of the arrangement. `slot` is the position along the axis (0 = first end,
    1 = other end), `stack_index` orders bearings sharing a slot: a slot with two bearings is double-stacked.
    The same bearing can appear more than once in an arrangement.
    """
    __tablename__ = "arrangement_bearings"
    __table_args__ = (
        UniqueConstraint("arrangement_id", "slot", "stack_index", name="uq_arrangement_slot_stack"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    arrangement_id: Mapped[int] = mapped_column(ForeignKey("arrangements.id", ondelete="CASCADE"), nullable=False)
    project_bearing_id: Mapped[int] = mapped_column(ForeignKey("project_bearings.id", ondelete="RESTRICT"), nullable=False)
    slot: Mapped[int] = mapped_column(Integer, nullable=False)
    stack_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

class CartEdit(Base):
    """
    A change made by hand to the cart that the rules compute for a project. `key` names the computed line it
    changes, or is "added:<sku>" for a piece added by hand. A quantity of 0 removes the line.
    """
    __tablename__ = "cart_edits"
    __table_args__ = (
        UniqueConstraint("project_id", "key", name="uq_cart_edit"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    sku: Mapped[Optional[str]] = mapped_column(Text)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)


# -----------------------------
# Pydantic schemas
# -----------------------------
class CartEditIn(BaseModel):
    key: Optional[str] = None      # line to change; leave empty to add a piece by hand
    sku: Optional[str] = None      # catalogue piece chosen for the line; empty keeps the computed one
    qty: int

class ProjectCreationRequest(BaseModel):
    title: str
    url: str

class ArrangementBSBIn(BaseModel):
    has_spacer: Optional[bool] = None
    spacer_len_ge_10mm: Optional[bool] = None
    spacer_mobility: Optional[str] = None  # 'moves' | 'stuck'

class ArrangementOAIn(BaseModel):
    axle_length: Optional[str] = None      # 'short' | 'long'

class ArrangementFreehubIn(BaseModel):
    body: Optional[str] = None             # 'hg_microspline' | 'xd_xdr'
    one_side: Optional[bool] = None        # both bearings installed from the same side

class ArrangementIn(BaseModel):
    project_id: int
    name: str
    material: str              # 'carbon' | 'alloy'
    type: str                  # 'SP' | 'BSB' | 'OA'
    slots: List[List[str]]     # bearing codes per position, e.g. [["6902", "6902"], ["6902"]]
    component: str             # 'frame' | 'hub' | 'freehub'
    has_center_lock: Optional[bool] = None
    freehub: Optional[ArrangementFreehubIn] = None
    bsb: Optional[ArrangementBSBIn] = None
    oa: Optional[ArrangementOAIn] = None


# -----------------------------
# Helper: save PDF and make a unique filename
# -----------------------------
def _save_pdf_bytes(diagram_url: str, pdf_bytes: bytes) -> str:
    # Stable-ish unique name from url + timestamp (down to seconds)
    h = hashlib.sha256((diagram_url + "::" + datetime.utcnow().isoformat(timespec="seconds")).encode()).hexdigest()[:16]
    filename = f"diagram_{h}.pdf"
    out_path = DIAGRAMS_DIR / filename
    with open(out_path, "wb") as f:
        f.write(pdf_bytes)
    return str(out_path)


# =========================
# FastAPI app
# =========================
app = FastAPI(title="Bearing Identification API")
app.mount("/static/diagrams", StaticFiles(directory="app/backend/data/diagrams"), name="diagrams")
# the instructional diagrams of altalt.ca, one image per job that has an official drawing
app.mount("/static/instruction-diagrams", StaticFiles(directory="data/altalt_site/instructions/png"), name="instruction-diagrams")


# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React app URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def init_db() -> None:
    """Create all tables if not present (idempotent)."""
    Base.metadata.create_all(bind=engine)

@app.on_event("startup")
def on_startup():
    init_db()
    DIAGRAMS_DIR.mkdir(parents=True, exist_ok=True)


def _known_dimensions(code: str) -> Optional[dict]:
    """Dimensions already stored for a bearing code, so a code is only ever looked up once."""
    with SessionLocal() as db:
        b = db.query(Bearing).filter(Bearing.code == code).one_or_none()
        if b is None or b.inner_diameter is None:
            return None
        return {
            "inner_diameter": float(b.inner_diameter),
            "outer_diameter": float(b.outer_diameter),
            "width": float(b.width),
            "extended_inner_ring_width": b.extended_inner_ring_width and float(b.extended_inner_ring_width),
            "flange_diameter": b.flange_diameter and float(b.flange_diameter),
        }


@app.post("/create_project")
def create_project(request: ProjectCreationRequest):
    """
    It creates a new project in the app.
    It reads the given exploded diagram and finds the bearing codes, looking up on the web the ones
    that the diagram only gives a part number for.
    It finds the dimensions of these bearings.
    It highlights the bearing codes in the PDF.
    It saves this information in the database.
    """
    try:
        # read the diagram: bearing codes and their dimensions
        analysis, pdf_content = from_url_to_bearings(request.url, known_dimensions=_known_dimensions)
        # highlight bearing codes in the PDF
        highlighted_pdf_content = highlight_pdf(pdf_content, analysis)

        pdf_path = _save_pdf_bytes(request.url, highlighted_pdf_content)

        with SessionLocal.begin() as db:
            project = Project(
                title=request.title,
                diagram_url=request.url,
                diagram_pdf_path=pdf_path,
                manufacturer=analysis["manufacturer"],
                model=analysis["model"],
                unresolved_references=json.dumps(analysis["unresolved_references"]),
            )
            db.add(project)
            db.flush()  # to get project.id

            # Upsert each bearing, then link via project_bearings
            for item in analysis["bearings"]:
                b = db.query(Bearing).filter(Bearing.code == item["code"]).one_or_none()
                if b is None:
                    b = Bearing(code=item["code"])
                    db.add(b)
                # stored dimensions win; only a bearing that has none yet takes the ones just found
                if b.inner_diameter is None and item["dimensions"]:
                    dims = item["dimensions"]
                    b.inner_diameter = dims["inner_diameter"]
                    b.outer_diameter = dims["outer_diameter"]
                    b.width = dims["width"]
                    b.extended_inner_ring_width = dims["extended_inner_ring_width"]
                    b.flange_diameter = dims["flange_diameter"]
                    b.dimensions_source = item["dimensions_source"]
                    b.dimensions_source_url = item["dimensions_source_url"]
                db.flush()  # get b.id

                db.add(ProjectBearing(
                    project_id=project.id,
                    bearing_id=b.id,
                    quantity=item["quantity"],
                    found_in=item["found_in"],
                    reference=item["reference"],
                    source_url=item["source_url"],
                ))

        return {
            "status": "ok",
            "project_id": project.id,
            "diagram_pdf_path": pdf_path,
            "bearings_saved": [item["code"] for item in analysis["bearings"]],
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing diagram from URL: {str(e)}"
        )


@app.get("/projects")
def list_projects():
    with SessionLocal() as db:
        # bearings per project (codes)
        rows = db.execute(text("""
          SELECT p.id, p.title, p.diagram_url, p.diagram_pdf_path,
                 GROUP_CONCAT(b.code, '||') as codes
          FROM projects p
          LEFT JOIN project_bearings pb ON pb.project_id = p.id
          LEFT JOIN bearings b ON b.id = pb.bearing_id
          GROUP BY p.id
          ORDER BY p.id DESC
        """)).fetchall()
        out = []
        for r in rows:
            codes = (r.codes or "").split("||") if r.codes else []
            out.append({
                "id": r.id,
                "title": r.title,
                "diagram_url": r.diagram_url,
                "diagram_pdf_path": r.diagram_pdf_path,
                "bearing_codes": codes,
            })
        return out

@app.get("/projects/{project_id}")
def get_project(project_id: int):
    with SessionLocal() as db:
        p = db.query(Project).filter(Project.id == project_id).one_or_none()
        if not p:
            raise HTTPException(404, "Project not found")
        # bearings
        codes = [b.bearing.code for b in p.bearings]
        num = lambda x: None if x is None else float(x)
        bearings = [{
            "code": pb.bearing.code,
            "quantity": pb.quantity,
            "foundIn": pb.found_in,
            "reference": pb.reference,
            "sourceUrl": pb.source_url,
            "innerDiameter": num(pb.bearing.inner_diameter),
            "outerDiameter": num(pb.bearing.outer_diameter),
            "width": num(pb.bearing.width),
            "dimensionsSource": pb.bearing.dimensions_source,
            "dimensionsSourceUrl": pb.bearing.dimensions_source_url,
        } for pb in p.bearings]
        # arrangements
        arrs = []
        # basic rows
        arr_rows = db.query(Arrangement).filter(Arrangement.project_id == project_id).all()
        # map of arrangement_id -> bearing codes per slot, in stacking order
        slots_map = {}
        for ab, code in db.query(ArrangementBearing, Bearing.code)\
                    .join(ProjectBearing, ProjectBearing.id == ArrangementBearing.project_bearing_id)\
                    .join(Bearing, Bearing.id == ProjectBearing.bearing_id)\
                    .join(Arrangement, Arrangement.id == ArrangementBearing.arrangement_id)\
                    .filter(Arrangement.project_id == project_id)\
                    .order_by(ArrangementBearing.slot, ArrangementBearing.stack_index).all():
            slots_map.setdefault(ab.arrangement_id, {}).setdefault(ab.slot, []).append(code)

        # subtype detail helpers
        bsb_by_id = {x.arrangement_id: x for x in db.query(ArrangementBSB).all()}
        oa_by_id = {x.arrangement_id: x for x in db.query(ArrangementOA).all()}

        for a in arr_rows:
            by_slot = slots_map.get(a.id, {})
            slots = [by_slot.get(i, []) for i in range(SLOTS_BY_TYPE[a.type])]
            bsb = bsb_by_id.get(a.id)
            oa = oa_by_id.get(a.id)
            arrs.append({
                "id": str(a.id),
                "name": a.name,
                "material": a.material,
                "type": a.type,
                "slots": slots,
                "bsb": None if a.type != "BSB" else {
                    "hasSpacer": bsb.has_spacer if bsb else None,
                    "spacerLenGe10mm": bsb.spacer_len_ge_10mm if bsb else None,
                    "spacerMobility": bsb.spacer_mobility if bsb else None,
                },
                "oa": None if a.type != "OA" else {
                    "axleLength": oa.axle_length if oa else None,
                },
                "component": a.component,
                "hasCenterLock": a.has_center_lock,
                "freehub": None if a.component != "freehub" else {
                    "body": a.freehub_body,
                    "oneSide": a.freehub_one_side,
                },
            })
        return {
            "id": p.id,
            "title": p.title,
            "diagram_url": p.diagram_url,
            "diagram_pdf_path": p.diagram_pdf_path,
            "manufacturer": p.manufacturer,
            "model": p.model,
            "bearing_codes": codes,
            "bearings": bearings,
            "unresolved_references": json.loads(p.unresolved_references or "[]"),
            "arrangements": arrs,
        }


def _project_tools(project_id: int) -> List[dict]:
    """Runs the rule engine on every arrangement of the project."""
    with SessionLocal() as db:
        if not db.query(Project).filter(Project.id == project_id).one_or_none():
            raise HTTPException(404, "Project not found")
        num = lambda x: None if x is None else float(x)
        specs = []
        for a in db.query(Arrangement).filter(Arrangement.project_id == project_id).order_by(Arrangement.id).all():
            slots = [[] for _ in range(SLOTS_BY_TYPE[a.type])]
            rows = db.query(ArrangementBearing, Bearing)\
                     .join(ProjectBearing, ProjectBearing.id == ArrangementBearing.project_bearing_id)\
                     .join(Bearing, Bearing.id == ProjectBearing.bearing_id)\
                     .filter(ArrangementBearing.arrangement_id == a.id)\
                     .order_by(ArrangementBearing.slot, ArrangementBearing.stack_index).all()
            for ab, b in rows:
                slots[ab.slot].append(BearingSpec(code=b.code, inner=num(b.inner_diameter),
                                                  outer=num(b.outer_diameter), width=num(b.width)))
            bsb = db.query(ArrangementBSB).filter(ArrangementBSB.arrangement_id == a.id).one_or_none()
            oa = db.query(ArrangementOA).filter(ArrangementOA.arrangement_id == a.id).one_or_none()
            specs.append(ArrangementSpec(
                name=a.name, type=a.type, component=a.component, material=a.material, slots=slots,
                has_center_lock=a.has_center_lock, freehub_body=a.freehub_body, freehub_one_side=a.freehub_one_side,
                has_spacer=bsb.has_spacer if bsb else None,
                spacer_len_ge_10mm=bsb.spacer_len_ge_10mm if bsb else None,
                spacer_mobility=bsb.spacer_mobility if bsb else None,
                axle_length=oa.axle_length if oa else None,
            ))
        return [tools_for(spec) for spec in specs]


@app.get("/projects/{project_id}/tools")
def get_project_tools(project_id: int):
    """
    The press pieces needed for every arrangement of the project, job by job, and the cart that covers them all.
    """
    results = _project_tools(project_id)
    for result in results:
        for job in result["jobs"]:
            job["svg"] = svg_for(job)
            official = job["diagram"] if job["status"] == "diagram" else None
            job["diagram_url"] = f"/static/instruction-diagrams/{official[:-4]}.png" if official else None
    with SessionLocal() as db:
        edits = [{"key": e.key, "sku": e.sku, "qty": e.qty}
                 for e in db.query(CartEdit).filter(CartEdit.project_id == project_id).all()]
    return {"arrangements": results, "cart": apply_cart_edits(cart_for(results), edits)}


@app.get("/catalog")
def get_catalog():
    """Every individual piece that can be put in a cart."""
    return catalog_items()


@app.put("/projects/{project_id}/cart")
def edit_cart_line(project_id: int, payload: CartEditIn):
    """Changes one line of the project's cart: another piece or size, another quantity, or 0 to remove it."""
    if payload.sku is not None and payload.sku not in BY_SKU:
        raise HTTPException(400, f"Unknown piece: {payload.sku}")
    if payload.qty < 0:
        raise HTTPException(400, "Quantity cannot be negative")
    key = payload.key or (f"added:{payload.sku}" if payload.sku else None)
    if key is None:
        raise HTTPException(400, "Give the line to change, or the piece to add")
    with SessionLocal.begin() as db:
        if not db.query(Project).filter(Project.id == project_id).one_or_none():
            raise HTTPException(404, "Project not found")
        edit = db.query(CartEdit).filter(CartEdit.project_id == project_id, CartEdit.key == key).one_or_none()
        if edit is None:
            edit = CartEdit(project_id=project_id, key=key)
            db.add(edit)
        edit.sku, edit.qty = payload.sku, payload.qty
    return {"key": key}


@app.delete("/projects/{project_id}/cart")
def reset_cart_line(project_id: int, key: str):
    """Undoes the change made to a cart line (a piece added by hand disappears)."""
    with SessionLocal.begin() as db:
        db.query(CartEdit).filter(CartEdit.project_id == project_id, CartEdit.key == key).delete()
    return {"key": key}


@app.get("/projects/{project_id}/instructions", response_class=PlainTextResponse)
def get_project_instructions(project_id: int):
    """Step-by-step removal and install instructions for every arrangement of the project, as plain text."""
    return "\n\n".join(instructions_for(r) for r in _project_tools(project_id))


def _bearing_codes_to_project_bearing_ids(db: Session, project_id: int, codes: List[str]) -> List[int]:
    if not codes:
        return []
    q = db.query(ProjectBearing.id, Bearing.code)\
          .join(Bearing, Bearing.id == ProjectBearing.bearing_id)\
          .filter(ProjectBearing.project_id == project_id, Bearing.code.in_(codes))
    found = {code: pb_id for pb_id, code in q.all()}
    missing = [c for c in codes if c not in found]
    if missing:
        raise HTTPException(400, f"Codes not in this project: {missing}")
    return [found[c] for c in codes]


def _apply_arrangement_payload(db: Session, a: Arrangement, payload: ArrangementIn) -> None:
    """Copy the questionnaire answers onto the arrangement and rewrite its subtype rows and bearings."""
    if payload.type not in SLOTS_BY_TYPE:
        raise HTTPException(400, f"Unknown arrangement type: {payload.type}")
    if len(payload.slots) != SLOTS_BY_TYPE[payload.type]:
        raise HTTPException(400, f"{payload.type} needs {SLOTS_BY_TYPE[payload.type]} bearing position(s), got {len(payload.slots)}")

    a.name = payload.name
    a.material = payload.material
    a.type = payload.type
    a.component = payload.component
    a.has_center_lock = payload.has_center_lock if payload.component == "hub" else None
    is_freehub = payload.component == "freehub" and payload.freehub is not None
    a.freehub_body = payload.freehub.body if is_freehub else None
    a.freehub_one_side = payload.freehub.one_side if is_freehub else None
    db.flush()  # a.id

    # reset subtype rows
    db.query(ArrangementBSB).filter(ArrangementBSB.arrangement_id == a.id).delete()
    db.query(ArrangementOA).filter(ArrangementOA.arrangement_id == a.id).delete()
    if a.type == "BSB" and payload.bsb:
        db.add(ArrangementBSB(
            arrangement_id=a.id,
            has_spacer=bool(payload.bsb.has_spacer),
            spacer_len_ge_10mm=payload.bsb.spacer_len_ge_10mm,
            spacer_mobility=payload.bsb.spacer_mobility,
        ))
    if a.type == "OA" and payload.oa and payload.oa.axle_length:
        db.add(ArrangementOA(arrangement_id=a.id, axle_length=payload.oa.axle_length))

    # reset bearings
    db.query(ArrangementBearing).filter(ArrangementBearing.arrangement_id == a.id).delete()
    for slot, codes in enumerate(payload.slots):
        pb_ids = _bearing_codes_to_project_bearing_ids(db, a.project_id, codes)
        for stack_index, pb_id in enumerate(pb_ids):
            db.add(ArrangementBearing(
                arrangement_id=a.id,
                project_bearing_id=pb_id,
                slot=slot,
                stack_index=stack_index,
            ))


@app.post("/arrangements")
def create_arrangement(payload: ArrangementIn):
    with SessionLocal.begin() as db:
        a = Arrangement(project_id=payload.project_id)
        db.add(a)
        _apply_arrangement_payload(db, a, payload)
        return {"id": str(a.id)}


@app.put("/arrangements/{arrangement_id}")
def update_arrangement(arrangement_id: int, payload: ArrangementIn):
    with SessionLocal.begin() as db:
        a = db.query(Arrangement).filter(Arrangement.id == arrangement_id).one_or_none()
        if not a:
            raise HTTPException(404, "Arrangement not found")
        if a.project_id != payload.project_id:
            raise HTTPException(400, "project_id mismatch")
        _apply_arrangement_payload(db, a, payload)
        return {"id": str(a.id)}
