"""Population-exposure receptors (Phase L.1).

A `PopulatedPlace` is a town, village, or sensitive receptor (school,
hospital, drinking-water intake) whose proximity to a mine raises the
RCA's stringency. The platform uses these records to:

- Resolve per-station threshold overrides — RCAs typically impose
  stricter PM limits at residential receptors than at the mine fence
  (closes the K.2 J1-R4 follow-up: per-station, not just per-site).
- Compute a wind-aligned-population feature for the forecasting +
  attribution pipelines (the Caimanes-style cases turn on whether
  prevailing wind aligns the dust plume with a population center).
- Score regulatory severity in the K.2 compliance report (a breach at
  a station 800m from a town is not the same as one at the boundary
  fence).

Coordinates are WGS84 lon/lat per the K.3 GeoJSON contract on Zone +
HaulRoadSegment.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ReceptorKind = Literal[
    "town",            # populated locality
    "school",
    "hospital",
    "drinking_water_intake",
    "indigenous_community",
    "protected_area",
    "other",
]


class PopulatedPlaceSchema(BaseModel):
    """A receptor with location + population context.

    Source examples: INE census localidades / manzanas; SEA RCA
    receptor lists; hand-curated for sensitive infrastructure.
    """

    model_config = ConfigDict(from_attributes=True)

    place_id: str
    mine_id: str  # primary mine this receptor is tracked relative to
    name: str
    kind: ReceptorKind
    longitude: float = Field(ge=-180.0, le=180.0)
    latitude: float = Field(ge=-90.0, le=90.0)
    population: int | None = Field(default=None, ge=0)
    distance_to_mine_m: float | None = Field(default=None, ge=0.0)
    bearing_from_mine_deg: float | None = Field(
        default=None, ge=0.0, le=360.0
    )
    source: str = "ine"  # "ine" | "rca_receptor_list" | "manual"
    source_url: str | None = None
    notes: str | None = None


__all__ = [
    "PopulatedPlaceSchema",
    "ReceptorKind",
]
