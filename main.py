import hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, HttpUrl
import json
from sqlalchemy import (
    create_engine, Column, Integer, Text, Numeric, ForeignKey, JSON,
    UniqueConstraint, event, Enum as SAEnum, Boolean, text
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, Mapped, mapped_column, Session
from sqlalchemy.exc import IntegrityError
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.backend.llm.logic import from_url_to_bearings
from app.backend.utils import highlight_pdf
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
PieceFunction = SAEnum(
    "press", "leverage", "center", "clearance", "support", "extra",
    name="piece_function_t", native_enum=False
)
SizeType = SAEnum("ID", "OD", "ID_OD", "NONE", name="size_type_t", native_enum=False)
PhaseT = SAEnum("removal", "insertion", name="phase_t", native_enum=False)

# -----------------------------
# ORM models - these are the models that represent the tables of the database
# -----------------------------
class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    diagram_url: Mapped[str] = mapped_column(Text, nullable=False)
    diagram_pdf_path: Mapped[str] = mapped_column(Text, nullable=False)

    # this is like the opposite of a foreign key. This means this table has a relationship with the table ProjectBearing
    bearings: Mapped[List["ProjectBearing"]] = relationship(
        "ProjectBearing", back_populates="project", cascade="all, delete-orphan"
    )


class Bearing(Base):
    __tablename__ = "bearings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    inner_diameter: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    outer_diameter: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    width: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
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

    project: Mapped[Project] = relationship("Project", back_populates="bearings")
    bearing: Mapped[Bearing] = relationship("Bearing", back_populates="projects")


class Arrangement(Base):
    __tablename__ = "arrangements"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    material: Mapped[str] = mapped_column(material_t, nullable=False)
    type: Mapped[str] = mapped_column(arrangement_type_t, nullable=False)
    is_hub: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    has_center_lock: Mapped[bool | None] = mapped_column(Boolean)

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
    __tablename__ = "arrangement_bearings"
    arrangement_id: Mapped[int] = mapped_column(ForeignKey("arrangements.id", ondelete="CASCADE"), primary_key=True)
    project_bearing_id: Mapped[int] = mapped_column(ForeignKey("project_bearings.id", ondelete="RESTRICT"), primary_key=True)
    is_double_stacked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

# ========== Catalog ==========
class Piece(Base):
    __tablename__ = "pieces"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)  # e.g., 'drift_re'
    name: Mapped[str] = mapped_column(Text, nullable=False)
    function: Mapped[str] = mapped_column(PieceFunction, nullable=False)  # primary UI group
    pack_size: Mapped[int] = mapped_column(Integer, nullable=False, default=1)  # 2 for pairs (drift_re, over_axle_drift)
    meta: Mapped[dict | None] = mapped_column(JSON)

    variants: Mapped[list["PieceVariant"]] = relationship("PieceVariant", back_populates="piece", cascade="all, delete-orphan")

class PieceVariant(Base):
    __tablename__ = "piece_variants"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    piece_id: Mapped[int] = mapped_column(ForeignKey("pieces.id", ondelete="CASCADE"), nullable=False)
    size_type: Mapped[str] = mapped_column(SizeType, nullable=False)  # ID / OD / ID_OD / NONE
    size_id_mm: Mapped[int | None] = mapped_column(Integer)
    size_od_mm: Mapped[int | None] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    meta: Mapped[dict | None] = mapped_column(JSON)

    piece: Mapped["Piece"] = relationship("Piece", back_populates="variants")

# ========== Arrangement outputs ==========
class ArrangementRequiredPiece(Base):
    __tablename__ = "arrangement_required_pieces"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    arrangement_id: Mapped[int] = mapped_column(ForeignKey("arrangements.id", ondelete="CASCADE"), nullable=False)
    phase: Mapped[str] = mapped_column(PhaseT, nullable=False)  # removal | insertion
    piece_variant_id: Mapped[int | None] = mapped_column(ForeignKey("piece_variants.id", ondelete="RESTRICT"), nullable=True)

    # denormalized for fast UI grouping
    function: Mapped[str] = mapped_column(PieceFunction, nullable=False)  # copy from Piece.function
    quantity_units: Mapped[int] = mapped_column(Integer, nullable=False, default=1)  # count of sets (pack_size handled separately)
    bearing_code: Mapped[str | None] = mapped_column(Text)   # if derived from a specific bearing
    notes: Mapped[str | None] = mapped_column(Text)          # e.g., "=ID", ">ID", "<ID", "FD match", "hub substitution"

    piece_variant: Mapped["PieceVariant"] = relationship("PieceVariant")

# -----------------------------
# Pydantic schemas
# -----------------------------
class BearingDimensions(BaseModel):
    inner_diameter: float
    outer_diameter: float
    width: float
    # These may or may not be present in your enrichment step; keep optional
    extended_inner_ring_width: Optional[float] = None
    flange_diameter: Optional[float] = None

class BearingItem(BaseModel):
    code: str
    dimensions: BearingDimensions

class ProjectCreationRequest(BaseModel):
    title: str
    url: str

class ArrangementBSBIn(BaseModel):
    has_spacer: Optional[bool] = None
    spacer_len_ge_10mm: Optional[bool] = None
    spacer_mobility: Optional[str] = None  # 'moves' | 'stuck'

class ArrangementOAIn(BaseModel):
    axle_length: Optional[str] = None      # 'short' | 'long'

class ArrangementIn(BaseModel):
    project_id: int
    name: str
    material: str              # 'carbon' | 'alloy'
    type: str                  # 'SP' | 'BSB' | 'OA'
    selected_bearing_codes: List[str]
    double_stacked_codes: List[str] = []
    is_hub: Optional[bool] = None
    has_center_lock: Optional[bool] = None
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


CATALOG = {
    "pieces": [
        {"slug": "drift_re",        "name": "Drift RE (pair)",         "function": "press",  "pack_size": 2},
        {"slug": "pilot_short",     "name": "Pilot (Short)",           "function": "center"},
        {"slug": "pilot_long",      "name": "Pilot (Long)",            "function": "center"},
        {"slug": "sleeve",          "name": "Sleeve",                  "function": "leverage"},
        {"slug": "sleeve_long",     "name": "Sleeve (Long)",           "function": "leverage"},
        {"slug": "alt_ext",         "name": "ALT EXT",                 "function": "center"},
        {"slug": "alt_drift",       "name": "ALT Drift",               "function": "press"},
        {"slug": "alt_rod",         "name": "ALT Rod",                 "function": "press"},
        {"slug": "over_axle_drift", "name": "Over-Axle Drift (pair)",  "function": "clearance", "pack_size": 2},
        {"slug": "step",            "name": "Step",                    "function": "leverage"},
        {"slug": "stud",            "name": "Stud",                    "function": "support"},
        {"slug": "stud_stop",       "name": "Stud Stop",               "function": "support"},
        {"slug": "handle",          "name": "Handle",                  "function": "support"},
        {"slug": "spacer_tube",     "name": "Spacer Tube",             "function": "support"},
        {"slug": "o_ring_set",      "name": "O-Ring Set",              "function": "support"},
        {"slug": "sleeve_6",        "name": "Sleeve 6 (fixed)",        "function": "leverage",  "meta": {"fixed": True}},
        {"slug": "stop_oal",        "name": "Stop OAL (fixed)",        "function": "clearance", "meta": {"fixed": True, "also_centers": True}},
    ],
    "variants": {
        "drift_re":        {"size_type": "OD",    "ods": [16,19,21,22,24,26,28,30,32,35,37,41]},
        "pilot_short":     {"size_type": "ID",    "ids": [10,11,12,15,17,18,20,23,25], "meta":{"length":"short"}},
        "pilot_long":      {"size_type": "ID",    "ids": [10,11,12,15,17,18,20,23,25], "meta":{"length":"long"}},
        "sleeve":          {"size_type": "OD",    "ods": [16,19,22,24,26,28,30,32,35,37]},
        "sleeve_long":     {"size_type": "OD",    "ods": [16,19,22,24,26,28,30,32,35,37], "meta":{"length":"long"}},
        "alt_ext":         {"size_type": "ID",    "ids": [10,12,15,17,18,20,25]},
        "alt_drift":       {"size_type": "ID",    "ids": [15,17,18,20,25]},
        "over_axle_drift": {"size_type": "ID_OD", "id_od": [[15,24],[15,26],[15,28],[15,30],[15,32],[17,26],[17,28],[17,30],[17,35],[18,30],[18,32],[20,32],[20,37],[25,37]]},
        # fixed-size pieces (no variants needed): step, stud, stud_stop, handle, spacer_tube, o_ring_set, sleeve_6, stop_oal
    }
}

def seed_catalog(db: Session):
    # upsert pieces
    existing = {p.slug: p for p in db.query(Piece).all()}
    for p in CATALOG["pieces"]:
        piece = existing.get(p["slug"])
        if not piece:
            piece = Piece(slug=p["slug"], name=p["name"], function=p["function"], pack_size=p.get("pack_size", 1), meta=p.get("meta"))
            db.add(piece); db.flush()
            existing[p["slug"]] = piece
        else:
            piece.name = p["name"]
            piece.function = p["function"]
            piece.pack_size = p.get("pack_size", piece.pack_size)
            piece.meta = p.get("meta")
            db.flush()

    # upsert variants
    for slug, spec in CATALOG.get("variants", {}).items():
        piece = existing[slug]
        st = spec["size_type"]
        # clear & recreate (simple)
        db.query(PieceVariant).filter(PieceVariant.piece_id == piece.id).delete()
        if st == "ID":
            for v in spec["ids"]:
                db.add(PieceVariant(piece_id=piece.id, size_type="ID", size_id_mm=v, size_od_mm=None,
                                    label=f"{piece.name} {v} mm", meta=spec.get("meta")))
        elif st == "OD":
            for v in spec["ods"]:
                db.add(PieceVariant(piece_id=piece.id, size_type="OD", size_id_mm=None, size_od_mm=v,
                                    label=f"{piece.name} {v} mm", meta=spec.get("meta")))
        elif st == "ID_OD":
            for id_mm, od_mm in spec["id_od"]:
                db.add(PieceVariant(piece_id=piece.id, size_type="ID_OD", size_id_mm=id_mm, size_od_mm=od_mm,
                                    label=f"{piece.name} {id_mm}×{od_mm} mm", meta=spec.get("meta")))
        else:
            raise ValueError(f"Unknown size_type {st}")

    FIXED_WITH_VARIANTS = [
        "step", "stud", "stud_stop", "handle",
        "spacer_tube", "o_ring_set", "sleeve_6", "stop_oal"
    ]

    for slug in FIXED_WITH_VARIANTS:
        piece = existing[slug]
        has = db.query(PieceVariant).filter(
            PieceVariant.piece_id == piece.id, PieceVariant.size_type == "NONE"
        ).first()
        if not has:
            db.add(PieceVariant(
                piece_id=piece.id, size_type="NONE",
                size_id_mm=None, size_od_mm=None,
                label=piece.name, meta=None
            ))


# ----- helpers -----
def pick_variant(db: Session, piece_slug: str, selector: dict, *, bearing: dict, phase: str) -> Tuple[Piece, PieceVariant | None, str]:
    """
    selector: {"by": "ID"|"OD"|"ID_OD"|"OD_OR_FD_REMOVE", "mode": "="|">"| "<", "delta": int?}
    bearing: {"code": "...", "dimensions": {"inner_diameter": ID, "outer_diameter": OD, "width": W}, "flange_diameter": FD?}
    Returns (piece, variant or None, note)
    """
    piece = db.query(Piece).filter(Piece.slug == piece_slug).one()
    dim = bearing["dimensions"]
    ID = int(dim["inner_diameter"])
    OD = int(dim["outer_diameter"])
    FD = bearing.get("flange_diameter")

    def choose_id(target, mode):
        ids = [v.size_id_mm for v in piece.variants if v.size_type == "ID"]
        ids = sorted(set(x for x in ids if x is not None))
        if mode == "=":
            val = target
            if val in ids: return val
        elif mode == ">":
            for v in ids:
                if v > target: return v
        elif mode == "<":
            for v in reversed(ids):
                if v < target: return v
        return None

    def choose_od(target, mode):
        ods = [v.size_od_mm for v in piece.variants if v.size_type == "OD"]
        ods = sorted(set(x for x in ods if x is not None))
        if mode == "=":
            val = target
            if val in ods: return val
        elif mode == ">":
            for v in ods:
                if v > target: return v
        elif mode == "<":
            for v in reversed(ods):
                if v < target: return v
        return None

    note = ""
    by = selector.get("by")
    mode = selector.get("mode", "=")
    delta = int(selector.get("delta", 0))

    if by == "ID":
        target = ID + delta
        chosen = choose_id(target, mode)
        if chosen is None:
            return piece, None, f"{mode}ID unavailable (target={target})"
        variant = db.query(PieceVariant).filter(
            PieceVariant.piece_id == piece.id, PieceVariant.size_type == "ID", PieceVariant.size_id_mm == chosen
        ).first()
        note = f"{mode}ID" if delta == 0 else f"{mode}ID (Δ{delta}mm)"
        return piece, variant, note

    if by == "OD":
        target = OD + delta
        chosen = choose_od(target, mode)
        if chosen is None:
            return piece, None, f"{mode}OD unavailable (target={target})"
        variant = db.query(PieceVariant).filter(
            PieceVariant.piece_id == piece.id, PieceVariant.size_type == "OD", PieceVariant.size_od_mm == chosen
        ).first()
        note = f"{mode}OD" if delta == 0 else f"{mode}OD (Δ{delta}mm)"
        return piece, variant, note

    if by == "OD_OR_FD_REMOVE":
        # removal sleeves: use flange diameter if present
        use = FD if (phase == "removal" and FD) else OD
        chosen = choose_od(use, "=")
        if chosen is None:
            return piece, None, f"=OD/FD unavailable (target={use})"
        variant = db.query(PieceVariant).filter(
            PieceVariant.piece_id == piece.id, PieceVariant.size_type == "OD", PieceVariant.size_od_mm == chosen
        ).first()
        note = "FD match" if (phase == "removal" and FD) else "=OD"
        return piece, variant, note

    if by == "ID_OD":
        # exact tuple match for OA drifts
        variant = db.query(PieceVariant).filter(
            PieceVariant.piece_id == piece.id,
            PieceVariant.size_type == "ID_OD",
            PieceVariant.size_id_mm == ID,
            PieceVariant.size_od_mm == OD
        ).first()
        if not variant:
            return piece, None, f"ID×OD unavailable ({ID}×{OD})"
        return piece, variant, "ID×OD"

    raise HTTPException(400, f"Unknown selector.by {by}")

def add_row(rows, *, piece: Piece, variant: PieceVariant | None, function: str, bearing_code: str | None, notes: str | None, quantity_units: int = 1):
    rows.append({
        "piece_id": piece.id, "piece_variant_id": variant.id if variant else None,
        "function": function, "bearing_code": bearing_code, "notes": notes, "quantity_units": quantity_units
    })

# ----- resolver core -----
def resolve_and_persist_arrangement_pieces(db: Session, arrangement: Arrangement):
    """
    Uses the selected bearings for this arrangement (arrangement_bearings table) and rules to
    write ArrangementRequiredPiece rows for removal & insertion.
    """
    # 0) load bearings selected for this arrangement
    # map PB -> Bearing, include optional FD if present on your Bearing model (use extended field name)
    ab_rows = db.query(ArrangementBearing, ProjectBearing, Bearing)\
        .join(ProjectBearing, ProjectBearing.id == ArrangementBearing.project_bearing_id)\
        .join(Bearing, Bearing.id == ProjectBearing.bearing_id)\
        .filter(ArrangementBearing.arrangement_id == arrangement.id).all()

    if not ab_rows:
        # no bearings selected -> nothing to compute
        db.query(ArrangementRequiredPiece).filter(ArrangementRequiredPiece.arrangement_id == arrangement.id).delete()
        return

    # lift flags
    is_sp = arrangement.type == "SP"
    is_bsb = arrangement.type == "BSB"
    is_oa = arrangement.type == "OA"
    oa_long = False
    if is_oa:
        oa = db.query(ArrangementOA).filter(ArrangementOA.arrangement_id == arrangement.id).first()
        oa_long = (oa and oa.axle_length == "long")

    # find double-stacked bearing codes for this arrangement (subset)
    double_codes = set()
    for ab, pb, b in ab_rows:
        if ab.is_double_stacked:
            double_codes.add(b.code)

    # utility to iterate bearings for selection (per your UI, we apply rules to each selected bearing)
    def each_bearing():
        for ab, pb, b in ab_rows:
            bearing_obj = {
                "code": b.code,
                "dimensions": {"inner_diameter": b.inner_diameter, "outer_diameter": b.outer_diameter, "width": b.width},
                "flange_diameter": b.flange_diameter  # may be None
            }
            yield bearing_obj

    # 1) build rows per phase
    def build_phase(phase: str) -> list[dict]:
        rows: list[dict] = []

        # ----- GLOBAL DEFAULTS (every configuration) -----
        # 2x Spacer Tube (support, fixed)
        spacer_piece = db.query(Piece).filter(Piece.slug == "spacer_tube").one()
        spacer_variant = db.query(PieceVariant).filter(PieceVariant.piece_id == spacer_piece.id).first()
        add_row(rows, piece=spacer_piece, variant=spacer_variant,
                function=spacer_piece.function, bearing_code=None, notes=None, quantity_units=2)
        # 1x O-Ring set (support, fixed)
        oring_piece = db.query(Piece).filter(Piece.slug == "o_ring_set").one()
        oring_variant = db.query(PieceVariant).filter(PieceVariant.piece_id == oring_piece.id).first()
        add_row(rows, piece=oring_piece, variant=oring_variant,
                function=oring_piece.function, bearing_code=None, notes=None, quantity_units=1)

        # ----- RULES PER ARRANGEMENT -----

        # SIMPLE PIVOT
        if is_sp:
            # branch double-stacked or standard
            # decide by: any selected bearing is flagged double-stacked
            sp_double = len(double_codes) > 0

            if phase == "removal":
                if sp_double:
                    # Press/Center: ALT EXT = ID ; Leverage: SLEEVE=OD, STEP ; Support: STUD STOP
                    for bearing in each_bearing():
                        piece, variant, note = pick_variant(db, "alt_ext", {"by":"ID","mode":"="}, bearing=bearing, phase=phase)
                        add_row(rows, piece=piece, variant=variant, function=piece.function, bearing_code=bearing["code"], notes=note)
                        # sleeve (OD or FD on removal)
                        piece, variant, note = pick_variant(db, "sleeve", {"by":"OD_OR_FD_REMOVE"}, bearing=bearing, phase=phase)
                        add_row(rows, piece=piece, variant=variant, function="leverage", bearing_code=bearing["code"], notes=note)
                    add_row(rows, piece=db.query(Piece).filter_by(slug="step").one(), variant=None, function="leverage", bearing_code=None, notes=None)
                    add_row(rows, piece=db.query(Piece).filter_by(slug="stud_stop").one(), variant=None, function="support", bearing_code=None, notes=None)
                else:
                    # Press: LONG PILOT > ID ; Center: SHORT PILOT = ID ; Leverage: SLEEVE=OD, STEP ; Support: STUD, HANDLE, STUD STOP
                    for bearing in each_bearing():
                        piece, variant, note = pick_variant(db, "pilot_long", {"by":"ID","mode":">"}, bearing=bearing, phase=phase)
                        add_row(rows, piece=piece, variant=variant, function="press", bearing_code=bearing["code"], notes=note)
                        piece, variant, note = pick_variant(db, "pilot_short", {"by":"ID","mode":"="}, bearing=bearing, phase=phase)
                        add_row(rows, piece=piece, variant=variant, function="center", bearing_code=bearing["code"], notes=note)
                        piece, variant, note = pick_variant(db, "sleeve", {"by":"OD_OR_FD_REMOVE"}, bearing=bearing, phase=phase)
                        add_row(rows, piece=piece, variant=variant, function="leverage", bearing_code=bearing["code"], notes=note)
                    add_row(rows, piece=db.query(Piece).filter_by(slug="step").one(), variant=None, function="leverage", bearing_code=None, notes=None)
                    for slug in ("stud","handle","stud_stop"):
                        add_row(rows, piece=db.query(Piece).filter_by(slug=slug).one(), variant=None, function="support", bearing_code=None, notes=None)

            if phase == "insertion":
                # Press: DRIFT RE = OD ; Center: SHORT PILOT = ID ; Leverage: DRIFT RE = OD ; Support: STUD, STUD STOP, HANDLE
                for bearing in each_bearing():
                    piece, variant, note = pick_variant(db, "drift_re", {"by":"OD","mode":"="}, bearing=bearing, phase=phase)
                    add_row(rows, piece=piece, variant=variant, function="press", bearing_code=bearing["code"], notes=note)
                    piece, variant, note = pick_variant(db, "pilot_short", {"by":"ID","mode":"="}, bearing=bearing, phase=phase)
                    add_row(rows, piece=piece, variant=variant, function="center", bearing_code=bearing["code"], notes=note)
                    piece, variant, note = pick_variant(db, "drift_re", {"by":"OD","mode":"="}, bearing=bearing, phase=phase)
                    add_row(rows, piece=piece, variant=variant, function="leverage", bearing_code=bearing["code"], notes=note)
                for slug in ("stud","stud_stop","handle"):
                    add_row(rows, piece=db.query(Piece).filter_by(slug=slug).one(), variant=None, function="support", bearing_code=None, notes=None)

        # OVER-AXLE
        if is_oa:
            if oa_long:
                if phase == "removal":
                    for bearing in each_bearing():
                        # Press: DRIFT RE > ID
                        piece, variant, note = pick_variant(db, "drift_re", {"by":"ID","mode":">"}, bearing=bearing, phase=phase)
                        add_row(rows, piece=piece, variant=variant, function="press", bearing_code=bearing["code"], notes=note)
                        # Center: 2 × LONG PILOT < ID
                        for _ in range(2):
                            piece, variant, note = pick_variant(db, "pilot_long", {"by":"ID","mode":"<"}, bearing=bearing, phase=phase)
                            add_row(rows, piece=piece, variant=variant, function="center", bearing_code=bearing["code"], notes=note)
                        # Leverage: LONG SLEEVE, STEP
                        piece, variant, note = pick_variant(db, "sleeve_long", {"by":"OD_OR_FD_REMOVE"}, bearing=bearing, phase=phase)
                        add_row(rows, piece=piece, variant=variant, function="leverage", bearing_code=bearing["code"], notes=note)
                    add_row(rows, piece=db.query(Piece).filter_by(slug="step").one(), variant=None, function="leverage", bearing_code=None, notes=None)
                    for slug in ("handle","stud_stop","stud"):
                        add_row(rows, piece=db.query(Piece).filter_by(slug=slug).one(), variant=None, function="support", bearing_code=None, notes=None)

                if phase == "insertion":
                    for bearing in each_bearing():
                        # Press: OVER-AXLE DRIFT = ID×OD, DRIFT RE = OD
                        piece, variant, note = pick_variant(db, "over_axle_drift", {"by":"ID_OD"}, bearing=bearing, phase=phase)
                        add_row(rows, piece=piece, variant=variant, function="press", bearing_code=bearing["code"], notes=note)
                        piece, variant, note = pick_variant(db, "drift_re", {"by":"OD","mode":"="}, bearing=bearing, phase=phase)
                        add_row(rows, piece=piece, variant=variant, function="press", bearing_code=bearing["code"], notes=note)
                        # Center: 2 × LONG PILOT < ID
                        for _ in range(2):
                            piece, variant, note = pick_variant(db, "pilot_long", {"by":"ID","mode":"<"}, bearing=bearing, phase=phase)
                            add_row(rows, piece=piece, variant=variant, function="center", bearing_code=bearing["code"], notes=note)
                        # Leverage: OVER-AXLE DRIFT, DRIFT RE
                        piece, variant, note = pick_variant(db, "over_axle_drift", {"by":"ID_OD"}, bearing=bearing, phase=phase)
                        add_row(rows, piece=piece, variant=variant, function="clearance", bearing_code=bearing["code"], notes=note)
                        piece, variant, note = pick_variant(db, "drift_re", {"by":"OD","mode":"="}, bearing=bearing, phase=phase)
                        add_row(rows, piece=piece, variant=variant, function="leverage", bearing_code=bearing["code"], notes=note)
                    for slug in ("stud","stud_stop","handle"):
                        add_row(rows, piece=db.query(Piece).filter_by(slug=slug).one(), variant=None, function="support", bearing_code=None, notes=None)

            else:
                # OA SHORT
                if phase == "removal":
                    for bearing in each_bearing():
                        # Press: LONG PILOT = ID
                        piece, variant, note = pick_variant(db, "pilot_long", {"by":"ID","mode":"="}, bearing=bearing, phase=phase)
                        add_row(rows, piece=piece, variant=variant, function="press", bearing_code=bearing["code"], notes=note)
                        # Center: 2 × LONG PILOT < ID
                        for _ in range(2):
                            piece, variant, note = pick_variant(db, "pilot_long", {"by":"ID","mode":"<"}, bearing=bearing, phase=phase)
                            add_row(rows, piece=piece, variant=variant, function="center", bearing_code=bearing["code"], notes=note)
                        # Leverage: SLEEVE, STEP
                        piece, variant, note = pick_variant(db, "sleeve", {"by":"OD_OR_FD_REMOVE"}, bearing=bearing, phase=phase)
                        add_row(rows, piece=piece, variant=variant, function="leverage", bearing_code=bearing["code"], notes=note)
                    add_row(rows, piece=db.query(Piece).filter_by(slug="step").one(), variant=None, function="leverage", bearing_code=None, notes=None)
                    for slug in ("stud","stud_stop","handle"):
                        add_row(rows, piece=db.query(Piece).filter_by(slug=slug).one(), variant=None, function="support", bearing_code=None, notes=None)

                if phase == "insertion":
                    for bearing in each_bearing():
                        # Press: DRIFT RE = OD
                        piece, variant, note = pick_variant(db, "drift_re", {"by":"OD","mode":"="}, bearing=bearing, phase=phase)
                        add_row(rows, piece=piece, variant=variant, function="press", bearing_code=bearing["code"], notes=note)
                        # Center: 2× LONG PILOT = ID; SHORT PILOT = ID
                        piece, variant, note = pick_variant(db, "pilot_long", {"by":"ID","mode":"="}, bearing=bearing, phase=phase)
                        add_row(rows, piece=piece, variant=variant, function="center", bearing_code=bearing["code"], notes=note)
                        piece, variant, note = pick_variant(db, "pilot_long", {"by":"ID","mode":"="}, bearing=bearing, phase=phase)
                        add_row(rows, piece=piece, variant=variant, function="center", bearing_code=bearing["code"], notes=note)
                        piece, variant, note = pick_variant(db, "pilot_short", {"by":"ID","mode":"="}, bearing=bearing, phase=phase)
                        add_row(rows, piece=piece, variant=variant, function="center", bearing_code=bearing["code"], notes=note)
                        # Leverage: DRIFT RE = OD
                        piece, variant, note = pick_variant(db, "drift_re", {"by":"OD","mode":"="}, bearing=bearing, phase=phase)
                        add_row(rows, piece=piece, variant=variant, function="leverage", bearing_code=bearing["code"], notes=note)
                    for slug in ("stud","stud_stop","handle"):
                        add_row(rows, piece=db.query(Piece).filter_by(slug=slug).one(), variant=None, function="support", bearing_code=None, notes=None)

        # BSB
        if is_bsb:
            # inspect your BSB subtype from arrangement_bsb table
            bsb = db.query(ArrangementBSB).filter(ArrangementBSB.arrangement_id == arrangement.id).first()
            spacer = (bsb.has_spacer if bsb else None)
            spacer_ge10 = (bsb.spacer_len_ge_10mm if bsb else None)
            mobility = (bsb.spacer_mobility if bsb else None)

            if phase == "removal":
                if (spacer is False) or (mobility == "moves"):
                    # NO SPACER / SPACER THAT MOVES
                    for bearing in each_bearing():
                        add_row(rows, piece=db.query(Piece).filter_by(slug="alt_rod").one(), variant=None, function="press", bearing_code=None, notes=None)
                        piece, variant, note = pick_variant(db, "alt_drift", {"by":"ID","mode":"="}, bearing=bearing, phase=phase)
                        add_row(rows, piece=piece, variant=variant, function="press", bearing_code=bearing["code"], notes=note)
                        piece, variant, note = pick_variant(db, "sleeve", {"by":"OD_OR_FD_REMOVE"}, bearing=bearing, phase=phase)
                        add_row(rows, piece=piece, variant=variant, function="leverage", bearing_code=bearing["code"], notes=note)
                    add_row(rows, piece=db.query(Piece).filter_by(slug="step").one(), variant=None, function="leverage", bearing_code=None, notes=None)
                    add_row(rows, piece=db.query(Piece).filter_by(slug="stud_stop").one(), variant=None, function="support", bearing_code=None, notes=None)
                else:
                    # SPACER STUCK or DOUBLE-STACKED
                    for bearing in each_bearing():
                        piece, variant, note = pick_variant(db, "alt_ext", {"by":"ID","mode":"="}, bearing=bearing, phase=phase)
                        add_row(rows, piece=piece, variant=variant, function="center", bearing_code=bearing["code"], notes=note)
                        piece, variant, note = pick_variant(db, "sleeve", {"by":"OD_OR_FD_REMOVE"}, bearing=bearing, phase=phase)
                        add_row(rows, piece=piece, variant=variant, function="leverage", bearing_code=bearing["code"], notes=note)
                    add_row(rows, piece=db.query(Piece).filter_by(slug="step").one(), variant=None, function="leverage", bearing_code=None, notes=None)
                    add_row(rows, piece=db.query(Piece).filter_by(slug="stud_stop").one(), variant=None, function="support", bearing_code=None, notes=None)

            if phase == "insertion":
                for bearing in each_bearing():
                    piece, variant, note = pick_variant(db, "drift_re", {"by":"OD","mode":"="}, bearing=bearing, phase=phase)
                    add_row(rows, piece=piece, variant=variant, function="press", bearing_code=bearing["code"], notes=note)
                    piece, variant, note = pick_variant(db, "pilot_short", {"by":"ID","mode":"="}, bearing=bearing, phase=phase)
                    add_row(rows, piece=piece, variant=variant, function="center", bearing_code=bearing["code"], notes=note)
                    piece, variant, note = pick_variant(db, "pilot_long", {"by":"ID","mode":"="}, bearing=bearing, phase=phase)
                    add_row(rows, piece=piece, variant=variant, function="center", bearing_code=bearing["code"], notes=note)
                    piece, variant, note = pick_variant(db, "drift_re", {"by":"OD","mode":"="}, bearing=bearing, phase=phase)
                    add_row(rows, piece=piece, variant=variant, function="leverage", bearing_code=bearing["code"], notes=note)
                for slug in ("stud","stud_stop","handle"):
                    add_row(rows, piece=db.query(Piece).filter_by(slug=slug).one(), variant=None, function="support", bearing_code=None, notes=None)

        # ----- HUB substitutions -----
        if arrangement.is_hub:
            # load hub flags (we stored has_center_lock nullable)
            has_cl = arrangement.has_center_lock is True
            arr_type = arrangement.type
            # substitute sleeves in rows
            new_rows = []
            for r in rows:
                pv = db.query(PieceVariant).get(r["piece_variant_id"]) if r["piece_variant_id"] else None
                piece = db.query(Piece).get(r["piece_id"])

                # only intercept sleeves (leverage group) produced earlier
                if piece.slug in ("sleeve","sleeve_long") and piece.function == "leverage":
                    if has_cl:
                        # replace sleeve -> sleeve_long (keep size if any)
                        rep_piece = db.query(Piece).filter_by(slug="sleeve_long").one()
                        rep_variant = None
                        if pv and pv.size_type == "OD":
                            rep_variant = db.query(PieceVariant).filter_by(piece_id=rep_piece.id, size_type="OD", size_od_mm=pv.size_od_mm).first()
                        new_rows.append({**r, "piece_id": rep_piece.id, "piece_variant_id": rep_variant.id if rep_variant else None, "notes": (r["notes"] or "") + " (hub centerlock→long sleeve)"})
                    else:
                        if arr_type == "OA":
                            # replace with STOP OAL (fixed, clearance/center)
                            rep_piece = db.query(Piece).filter_by(slug="stop_oal").one()
                            new_rows.append({**r, "piece_id": rep_piece.id, "piece_variant_id": None, "function": rep_piece.function, "notes": (r["notes"] or "") + " (hub no-CL→STOP OAL)"})
                        else:
                            # SP/BSB → Sleeve 6 (fixed)
                            rep_piece = db.query(Piece).filter_by(slug="sleeve_6").one()
                            new_rows.append({**r, "piece_id": rep_piece.id, "piece_variant_id": None, "notes": (r["notes"] or "") + " (hub no-CL→SLEEVE 6)"})
                else:
                    new_rows.append(r)
            rows = new_rows

        return rows

    # wipe old
    db.query(ArrangementRequiredPiece).filter(ArrangementRequiredPiece.arrangement_id == arrangement.id).delete()

    # build & persist both phases
    for phase in ("removal", "insertion"):
        rows = build_phase(phase)
        for r in rows:
            # if variant missing (no available size), still record as note for UI
            pv_id = r["piece_variant_id"]
            db.add(ArrangementRequiredPiece(
                arrangement_id=arrangement.id, phase=phase,
                piece_variant_id=pv_id,
                function=r["function"], quantity_units=r["quantity_units"], bearing_code=r["bearing_code"], notes=r["notes"]
            ))



# =========================
# FastAPI app
# =========================
app = FastAPI(title="Bearing Identification API")
app.mount("/static/diagrams", StaticFiles(directory="app/backend/data/diagrams"), name="diagrams")


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
    with SessionLocal.begin() as db:
        seed_catalog(db)


@app.post("/create_project")
async def create_project(request: ProjectCreationRequest):
    """
    It creates a new project in the app.
    It takes the given exploded diagram, extracts text and finds bearing codes.
    It looks for dimensions of these bearings in the web.
    It highlights the bearing codes in the PDF.
    It saves this information in the database.
    """
    try:
        # process PDF and get bearing information
        bearing_info, pdf_content = from_url_to_bearings(request.url)
        # highlight bearing codes in the PDF
        highlighted_pdf_content = highlight_pdf(pdf_content, bearing_info)

        # Normalize to our Pydantic models (also validates)
        normalized_bearings: List[BearingItem] = []

        for item in bearing_info["bearings"]:
            dims = item.get("dimensions", {}) or {}

            normalized_bearings.append(
                BearingItem(
                    code=item["code"],
                    dimensions=BearingDimensions(
                        inner_diameter=dims["inner_diameter"],
                        outer_diameter=dims["outer_diameter"],
                        width=dims["width"],
                        extended_inner_ring_width=dims.get("extended_inner_ring_width"),
                        flange_diameter=dims.get("flange_diameter"),
                    ),
                )
            )

        # 3) Persist
        pdf_path = _save_pdf_bytes(request.url, highlighted_pdf_content)

        with SessionLocal.begin() as db:
            # Create project
            project = Project(
                title=request.title,
                diagram_url=request.url,
                diagram_pdf_path=pdf_path,
            )
            db.add(project)
            db.flush()  # to get project.id

            # Upsert each bearing, then link via project_bearings
            for bi in normalized_bearings:
                b = (
                    db.query(Bearing)
                    .filter(Bearing.code == bi.code)
                    .one_or_none()
                )
                if b is None:
                    # Insert new
                    b = Bearing(
                        code=bi.code,
                        inner_diameter=bi.dimensions.inner_diameter,
                        outer_diameter=bi.dimensions.outer_diameter,
                        width=bi.dimensions.width,
                        extended_inner_ring_width=bi.dimensions.extended_inner_ring_width,
                        flange_diameter=bi.dimensions.flange_diameter,
                    )
                    db.add(b)
                    try:
                        db.flush()  # get b.id; may raise IntegrityError if code was inserted concurrently
                    except IntegrityError:
                        db.rollback()
                        # someone else inserted concurrently; fetch it
                        with SessionLocal() as db2:
                            b = db2.query(Bearing).filter(Bearing.code == bi.code).one()

                # Link to this project (ignore if already linked)
                pb = (
                    db.query(ProjectBearing)
                    .filter(
                        ProjectBearing.project_id == project.id,
                        ProjectBearing.bearing_id == b.id,
                    )
                    .one_or_none()
                )
                if pb is None:
                    db.add(ProjectBearing(project_id=project.id, bearing_id=b.id))

        return {
            "status": "ok",
            "project_id": project.id,
            "diagram_pdf_path": pdf_path,
            "bearings_saved": [b.code for b in normalized_bearings],
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
        # arrangements
        arrs = []
        # basic rows
        arr_rows = db.query(Arrangement).filter(Arrangement.project_id == project_id).all()
        # map of arrangement_id -> double-stacked codes
        ds_map = {}
        for ab in db.query(ArrangementBearing, ProjectBearing, Bearing)\
                    .join(ProjectBearing, ProjectBearing.id == ArrangementBearing.project_bearing_id)\
                    .join(Bearing, Bearing.id == ProjectBearing.bearing_id)\
                    .join(Arrangement, Arrangement.id == ArrangementBearing.arrangement_id)\
                    .filter(Arrangement.project_id == project_id).all():
            arr_id = ab[0].arrangement_id
            ds_map.setdefault(arr_id, {"double": set(), "all": set()})
            ds_map[arr_id]["all"].add(ab[2].code)
            if ab[0].is_double_stacked:
                ds_map[arr_id]["double"].add(ab[2].code)

        # subtype detail helpers
        bsb_by_id = {x.arrangement_id: x for x in db.query(ArrangementBSB).all()}
        oa_by_id = {x.arrangement_id: x for x in db.query(ArrangementOA).all()}

        for a in arr_rows:
            all_codes = sorted(list(ds_map.get(a.id, {}).get("all", set())))
            ds_codes = sorted(list(ds_map.get(a.id, {}).get("double", set())))
            bsb = bsb_by_id.get(a.id)
            oa = oa_by_id.get(a.id)
            arrs.append({
                "id": str(a.id),
                "name": a.name,
                "material": a.material,
                "type": a.type,
                "selectedBearingCodes": all_codes,
                "doubleStackedCodes": ds_codes,
                "bsb": None if a.type != "BSB" else {
                    "hasSpacer": bsb.has_spacer if bsb else None,
                    "spacerLenGe10mm": bsb.spacer_len_ge_10mm if bsb else None,
                    "spacerMobility": bsb.spacer_mobility if bsb else None,
                },
                "oa": None if a.type != "OA" else {
                    "axleLength": oa.axle_length if oa else None,
                },
                "isHub": a.is_hub,
                "hasCenterLock": a.has_center_lock,
            })
        return {
            "id": p.id,
            "title": p.title,
            "diagram_url": p.diagram_url,
            "diagram_pdf_path": p.diagram_pdf_path,
            "bearing_codes": codes,
            "arrangements": arrs,
        }


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


@app.post("/arrangements")
def create_arrangement(payload: ArrangementIn):
    with SessionLocal.begin() as db:
        a = Arrangement(
            project_id=payload.project_id,
            name=payload.name,
            material=payload.material,
            type=payload.type,
            is_hub=bool(payload.is_hub),
            has_center_lock=payload.has_center_lock if payload.is_hub else None,
        )
        db.add(a)
        db.flush()  # a.id

        # subtype
        if a.type == "BSB" and payload.bsb:
            db.add(ArrangementBSB(
                arrangement_id=a.id,
                has_spacer=bool(payload.bsb.has_spacer),
                spacer_len_ge_10mm=payload.bsb.spacer_len_ge_10mm,
                spacer_mobility=payload.bsb.spacer_mobility,
            ))
        if a.type == "OA" and payload.oa and payload.oa.axle_length:
            db.add(ArrangementOA(arrangement_id=a.id, axle_length=payload.oa.axle_length))

        # bearings
        pb_ids_all = _bearing_codes_to_project_bearing_ids(db, a.project_id, payload.selected_bearing_codes)
        pb_ids_double = set(_bearing_codes_to_project_bearing_ids(db, a.project_id, payload.double_stacked_codes))
        for pb_id in pb_ids_all:
            db.add(ArrangementBearing(
                arrangement_id=a.id,
                project_bearing_id=pb_id,
                is_double_stacked=(pb_id in pb_ids_double),
            ))

        # compute pieces for this arrangement
        resolve_and_persist_arrangement_pieces(db, a)
        return {"id": str(a.id)}


@app.put("/arrangements/{arrangement_id}")
def update_arrangement(arrangement_id: int, payload: ArrangementIn):
    with SessionLocal.begin() as db:
        a = db.query(Arrangement).filter(Arrangement.id == arrangement_id).one_or_none()
        if not a:
            raise HTTPException(404, "Arrangement not found")
        if a.project_id != payload.project_id:
            raise HTTPException(400, "project_id mismatch")

        a.name = payload.name
        a.material = payload.material
        a.type = payload.type
        a.is_hub = bool(payload.is_hub)
        a.has_center_lock = payload.has_center_lock if payload.is_hub else None

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
        pb_ids_all = _bearing_codes_to_project_bearing_ids(db, a.project_id, payload.selected_bearing_codes)
        pb_ids_double = set(_bearing_codes_to_project_bearing_ids(db, a.project_id, payload.double_stacked_codes))
        for pb_id in pb_ids_all:
            db.add(ArrangementBearing(
                arrangement_id=a.id,
                project_bearing_id=pb_id,
                is_double_stacked=(pb_id in pb_ids_double),
            ))
        # ---- recompute pieces ----
        resolve_and_persist_arrangement_pieces(db, a)
        return {"id": str(a.id)}


@app.get("/projects/{project_id}/pieces_suggestions")
def pieces_suggestions(project_id: int):
    with SessionLocal() as db:
        # arrangements in project
        arrs = db.query(Arrangement).filter(Arrangement.project_id == project_id).all()
        out = []
        for a in arrs:
            # group by phase->function
            rows = db.query(ArrangementRequiredPiece, Piece, PieceVariant)\
                .join(PieceVariant, PieceVariant.id == ArrangementRequiredPiece.piece_variant_id, isouter=True)\
                .join(Piece, Piece.id == PieceVariant.piece_id, isouter=True)\
                .filter(ArrangementRequiredPiece.arrangement_id == a.id).all()

            grouped = {"removal": {"leverage": [], "press": [], "center": [], "clearance": [], "support": [], "extra": []},
                       "insertion": {"leverage": [], "press": [], "center": [], "clearance": [], "support": [], "extra": []}}
            for r, piece, variant in rows:
                entry = {
                    "piece": piece.name if piece else "Unknown",
                    "variant": variant.label if variant else None,
                    "quantity_sets": r.quantity_units,
                    "notes": r.notes,
                    "bearing_code": r.bearing_code
                }
                grouped[r.phase][r.function].append(entry)
            out.append({"arrangement_id": a.id, "name": a.name, **grouped})
        return out


@app.get("/projects/{project_id}/pieces_summary")
def pieces_summary(project_id: int):
    with SessionLocal() as db:
        # join all arrangements in project
        rows = db.execute(text("""
          SELECT arp.piece_variant_id, p.name as piece_name, pv.label as variant_label, p.function, p.pack_size,
                 SUM(arp.quantity_units) as qty_sets
          FROM arrangements a
          JOIN arrangement_required_pieces arp ON arp.arrangement_id = a.id
          JOIN piece_variants pv ON pv.id = arp.piece_variant_id
          JOIN pieces p ON p.id = pv.piece_id
          WHERE a.project_id = :pid
          GROUP BY arp.piece_variant_id, p.name, pv.label, p.function, p.pack_size
          ORDER BY p.function, p.name, pv.label
        """), {"pid": project_id}).fetchall()

        # also include fixed pieces with NONE variants (like sleeve_6, stop_oal, step, stud, etc.)
        fixed = db.execute(text("""
          SELECT 0 as piece_variant_id, p.name as piece_name, NULL as variant_label, p.function, p.pack_size,
                 COUNT(*) as qty_sets
          FROM arrangements a
          JOIN arrangement_required_pieces arp ON arp.arrangement_id = a.id
          JOIN pieces p ON p.id = (SELECT piece_id FROM piece_variants WHERE id = arp.piece_variant_id LIMIT 1)
          WHERE a.project_id = :pid AND NOT EXISTS (
              SELECT 1 FROM piece_variants pv WHERE pv.id = arp.piece_variant_id AND pv.size_type != 'NONE'
          )
          GROUP BY p.name, p.function, p.pack_size
        """), {"pid": project_id}).fetchall()

        # merge (simple)
        def pack(row):
            return {
                "piece": row.piece_name,
                "variant": row.variant_label,
                "function": row.function,
                "quantity_sets": int(row.qty_sets),
                "pack_size": int(row.pack_size)
            }
        grouped = [pack(r) for r in rows] + [pack(r) for r in fixed]
        return grouped


# todo add drag and drop with the mouse