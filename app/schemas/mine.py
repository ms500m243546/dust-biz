"""Mine + Zone schemas.

Static spatial entities. Per docs/data-contracts.md.

Phase K.3: zones and haul-road segments carry an optional GeoJSON
geometry field. The contract is the GeoJSON RFC 7946 subset DustOps
uses — Polygon for zones, LineString for haul-road segments —
validated by `geometry_validators.py`. Until a zone is migrated to
real geometry, the field stays None and the heuristic synthetic-grid
fallback in `app/domain/mine_state.py` continues to apply.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ZoneType = Literal[
    "pit",
    "haul_road",
    "stockpile",
    "dump",
    "crusher",
    "loading_area",
    "boundary",
]
OperationalImportance = Literal["low", "medium", "high", "critical"]
DustGenerationBaseline = Literal["low", "medium", "high"]
AutomationLevel = Literal["L0", "L1", "L2", "L3", "L4"]


class MineSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    mine_id: str
    name: str
    default_automation_level: AutomationLevel = "L1"


def _validate_polygon(geom: Any) -> Any:
    """Validate the GeoJSON Polygon subset DustOps accepts.

    Strict on the parts we use, lenient on the parts we don't. The
    coordinate reference system is implicitly WGS84 longitude/latitude
    per RFC 7946; any explicit `crs` field is ignored.
    """
    if geom is None:
        return None
    if not isinstance(geom, dict):
        raise ValueError("geometry must be a GeoJSON object")
    if geom.get("type") != "Polygon":
        raise ValueError("zone geometry must be of type Polygon")
    coords = geom.get("coordinates")
    if not isinstance(coords, list) or not coords:
        raise ValueError("Polygon coordinates must be a non-empty list of rings")
    for ring in coords:
        if not isinstance(ring, list) or len(ring) < 4:
            raise ValueError(
                "Polygon ring must have at least 4 positions (closed ring)"
            )
        if ring[0] != ring[-1]:
            raise ValueError("Polygon ring must be closed (first == last)")
        for pos in ring:
            if (
                not isinstance(pos, list)
                or len(pos) < 2
                or not all(isinstance(x, int | float) for x in pos[:2])
            ):
                raise ValueError("Polygon position must be [lon, lat]")
    return geom


def _validate_linestring(geom: Any) -> Any:
    if geom is None:
        return None
    if not isinstance(geom, dict):
        raise ValueError("geometry must be a GeoJSON object")
    if geom.get("type") != "LineString":
        raise ValueError("haul-road geometry must be of type LineString")
    coords = geom.get("coordinates")
    if not isinstance(coords, list) or len(coords) < 2:
        raise ValueError("LineString must have at least 2 positions")
    for pos in coords:
        if (
            not isinstance(pos, list)
            or len(pos) < 2
            or not all(isinstance(x, int | float) for x in pos[:2])
        ):
            raise ValueError("LineString position must be [lon, lat]")
    return geom


class ZoneSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    zone_id: str
    mine_id: str
    zone_type: ZoneType
    operational_importance: OperationalImportance
    dust_generation_baseline: DustGenerationBaseline
    allowed_interventions: tuple[str, ...] = Field(default_factory=tuple)
    requires_approval_for: tuple[str, ...] = Field(default_factory=tuple)
    geometry: dict[str, Any] | None = None

    @field_validator("geometry", mode="before")
    @classmethod
    def _check_geometry(cls, v: Any) -> Any:
        return _validate_polygon(v)


class HaulRoadSegmentSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    segment_id: str
    mine_id: str
    from_node: str
    to_node: str
    length_m: float
    surface_type: str
    geometry: dict[str, Any] | None = None

    @field_validator("geometry", mode="before")
    @classmethod
    def _check_geometry(cls, v: Any) -> Any:
        return _validate_linestring(v)
