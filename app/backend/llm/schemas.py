from typing import List

from pydantic import BaseModel, Field


class BearingDimensions(BaseModel):
    outer_diameter: int = Field(description="Outer diameter of the bearing.")
    inner_diameter: int = Field(description="Inner diameter of the bearing.")
    width: int = Field(description="Width of the bearing.")
    extended_inner_ring_width: int = Field(default=None, description="To be filled if the bearing has an extended inner ring.")
    flange_diameter: int = Field(default=None, description="To be filled if the bearing has a flange.")

class Bearing(BaseModel):
    code: str = Field(description="Code of the bearing.")
    dimensions: BearingDimensions = Field(description="Dimensions of the bearing.")

class Bearings(BaseModel):
    bearings: List[Bearing] = Field(
        description="List of bearings with their dimensions."
    )

class BearingCodes(BaseModel):
    codes: list[str] = Field(description="List of STANDARD bearing codes.")