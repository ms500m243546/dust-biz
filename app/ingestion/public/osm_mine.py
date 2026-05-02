"""OpenStreetMap mine-geometry connector (Phase L.4).

Pulls mine pit boundaries + haul-road segments from OSM via the
Overpass API. Output maps directly to the K.3 GeoJSON contract on
`Zone.geometry` (Polygon) and `HaulRoadSegment.geometry` (LineString).

OSM tag conventions used:
- Mine pits: `landuse=quarry` or `industrial=mine` polygons.
- Haul roads: `highway=service` + `service=mine` ways, or
  `highway=track` + `tracktype=grade*` ways inside the mine polygon.
- Mine boundary: outer ring of the `landuse=quarry` polygon.

Attribution: any UI displaying OSM-derived geometry must include
"© OpenStreetMap contributors" per the ODbL license — handled by
the dashboard footer once L.4 lands.

Like the SINCA / weather connectors, this module is a pure parser.
Tests use captured Overpass JSON; live network not used in CI.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app.ingestion.public import cache as ingest_cache

SOURCE_NAME = "osm"


@dataclass(frozen=True)
class OSMMineResult:
    """Output bundle: zone polygons + haul-road LineStrings."""

    zones: list[Mapping[str, Any]]
    haul_roads: list[Mapping[str, Any]]


def _node_lookup(elements: list[Mapping[str, Any]]) -> dict[int, tuple[float, float]]:
    """Build a node_id -> (lon, lat) lookup from a flat Overpass response."""
    out: dict[int, tuple[float, float]] = {}
    for el in elements:
        if el.get("type") != "node":
            continue
        nid = el.get("id")
        lon = el.get("lon")
        lat = el.get("lat")
        if (
            isinstance(nid, int)
            and isinstance(lon, int | float)
            and isinstance(lat, int | float)
            and not isinstance(lon, bool)
            and not isinstance(lat, bool)
        ):
            out[nid] = (float(lon), float(lat))
    return out


def _way_coords(
    way: Mapping[str, Any], nodes: dict[int, tuple[float, float]]
) -> list[list[float]]:
    nrefs = way.get("nodes")
    if not isinstance(nrefs, list):
        return []
    out: list[list[float]] = []
    for nid in nrefs:
        if not isinstance(nid, int):
            continue
        coord = nodes.get(nid)
        if coord is None:
            continue
        out.append([coord[0], coord[1]])
    return out


def parse_overpass_response(
    payload: Mapping[str, Any],
    *,
    mine_id: str,
) -> OSMMineResult:
    """Parse Overpass JSON into zone polygons + haul-road LineStrings.

    The Overpass response is a flat `elements` list of nodes + ways +
    relations. We resolve ways into coordinate arrays via the node
    lookup, then classify by tag set.
    """
    elements = payload.get("elements")
    if not isinstance(elements, list):
        return OSMMineResult(zones=[], haul_roads=[])

    nodes = _node_lookup(elements)
    zones: list[Mapping[str, Any]] = []
    haul_roads: list[Mapping[str, Any]] = []

    for el in elements:
        if el.get("type") != "way":
            continue
        tags = el.get("tags") or {}
        if not isinstance(tags, Mapping):
            continue
        coords = _way_coords(el, nodes)
        if len(coords) < 2:
            continue

        # Mine pit polygon
        is_pit = (
            tags.get("landuse") == "quarry"
            or tags.get("industrial") == "mine"
            or tags.get("man_made") == "mineshaft"
        )
        if is_pit and len(coords) >= 4:
            ring = coords[:]
            if ring[0] != ring[-1]:
                ring.append(ring[0])  # close the ring per GeoJSON RFC 7946
            zones.append(
                {
                    "zone_id": f"{mine_id}-pit-{el.get('id')}",
                    "mine_id": mine_id,
                    "zone_type": "pit",
                    "operational_importance": "high",
                    "dust_generation_baseline": "high",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [ring],
                    },
                    "osm_id": el.get("id"),
                    "osm_tags": dict(tags),
                }
            )
            continue

        # Haul road
        is_haul_road = (
            tags.get("highway") == "service" and tags.get("service") == "mine"
        ) or (tags.get("highway") == "track")
        if is_haul_road:
            haul_roads.append(
                {
                    "segment_id": f"{mine_id}-hrs-{el.get('id')}",
                    "mine_id": mine_id,
                    "from_node": str(coords[0]),
                    "to_node": str(coords[-1]),
                    "length_m": _length_m(coords),
                    "surface_type": str(tags.get("surface", "unknown")),
                    "geometry": {
                        "type": "LineString",
                        "coordinates": coords,
                    },
                    "osm_id": el.get("id"),
                }
            )

    return OSMMineResult(zones=zones, haul_roads=haul_roads)


def _length_m(coords: list[list[float]]) -> float:
    """Approximate length in metres (equirectangular at the local latitude)."""
    if len(coords) < 2:
        return 0.0
    import math

    R = 6_371_000.0
    total = 0.0
    for (lon1, lat1), (lon2, lat2) in zip(coords, coords[1:], strict=False):
        lat_mean = math.radians((lat1 + lat2) / 2.0)
        dx = math.radians(lon2 - lon1) * math.cos(lat_mean) * R
        dy = math.radians(lat2 - lat1) * R
        total += math.hypot(dx, dy)
    return total


class OSMMineConnector:
    source_name = SOURCE_NAME

    def __init__(self, *, cache_dir: Path) -> None:
        self.cache_dir = cache_dir

    def fetch_from_payload(
        self,
        *,
        payload: Mapping[str, Any],
        mine_id: str,
    ) -> OSMMineResult:
        return parse_overpass_response(payload, mine_id=mine_id)

    def fetch(
        self,
        *,
        window_from: datetime,
        window_to: datetime,
        **filters: object,
    ) -> Iterable[Mapping[str, Any]]:
        mine_id = filters.get("mine_id")
        if not isinstance(mine_id, str):
            raise TypeError("mine_id kwarg is required")
        cached = ingest_cache.get(
            source=SOURCE_NAME,
            window_from=window_from,
            window_to=window_to,
            filters={"mine_id": mine_id},
            cache_dir=self.cache_dir,
        )
        if cached is None:
            return iter(())
        result = self.fetch_from_payload(payload=cached, mine_id=mine_id)
        return iter(result.zones + result.haul_roads)


__all__ = [
    "SOURCE_NAME",
    "OSMMineConnector",
    "OSMMineResult",
    "parse_overpass_response",
]
