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
        return {"id": str(a.id)}


# todo add drag and drop with the mouse