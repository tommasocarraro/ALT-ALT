from typing import List, Optional

from pydantic import BaseModel, Field


# -----------------------------
# Step 1: what the model reads off the exploded diagram
# -----------------------------
class FoundBearing(BaseModel):
    code: str = Field(description="Bearing code exactly as it identifies the bearing, e.g. '6902 2RS' or '61804 2RSR'.")
    quantity: Optional[int] = Field(description="How many of this bearing the diagram lists, if stated.")
    page: Optional[int] = Field(description="1-based page where the code appears.")
    label: Optional[str] = Field(description="Position number or callout label attached to it in the diagram, if any.")


class PartReference(BaseModel):
    """A bearing the diagram shows without giving its code: only a part number, a kit name or a position."""
    ref_id: str = Field(description="Short id unique within this answer, e.g. 'ref-1'.")
    part_number: Optional[str] = Field(description="Manufacturer part number or kit number, if printed.")
    description: str = Field(description="How the diagram names the part, e.g. 'Main pivot bearing kit'.")
    quantity: Optional[int] = Field(description="How many, if stated.")
    page: Optional[int] = Field(description="1-based page where it appears.")


class DiagramExtraction(BaseModel):
    manufacturer: Optional[str] = Field(description="Bike or component manufacturer, if the diagram names it.")
    model: Optional[str] = Field(description="Model, model year or frame platform, if the diagram names it.")
    bearings: List[FoundBearing] = Field(description="Every distinct bearing code printed in the diagram.")
    unresolved_references: List[PartReference] = Field(
        description="Bearings that appear without a bearing code and need to be looked up."
    )


# -----------------------------
# Step 2: part references looked up on the web
# -----------------------------
class ResolvedReference(BaseModel):
    ref_id: str
    bearing_code: Optional[str] = Field(description="The bearing code this part corresponds to, or null if not found.")
    source_url: Optional[str] = Field(description="Page that states the bearing code.")
    note: Optional[str] = Field(description="Anything a person checking this should know.")


class ReferenceResolution(BaseModel):
    references: List[ResolvedReference]


# -----------------------------
# Step 3: dimensions of bearings that are not in the standard table
# -----------------------------
class WebDimensions(BaseModel):
    code: str
    inner_diameter: Optional[float] = Field(description="mm, or null if not found.")
    outer_diameter: Optional[float] = Field(description="mm, or null if not found.")
    width: Optional[float] = Field(description="mm, width of the outer ring, or null if not found.")
    extended_inner_ring_width: Optional[float] = Field(description="mm, only for bearings with an extended inner ring.")
    flange_diameter: Optional[float] = Field(description="mm, only for flanged bearings.")
    source_url: Optional[str] = Field(description="Page that states these dimensions.")


class DimensionLookup(BaseModel):
    bearings: List[WebDimensions]
