"""INE populated-places connector (Phase L.4).

Loads Chilean populated-place geometries from INE (Instituto Nacional
de Estadísticas) census exports. Each place becomes a `PopulatedPlace`
record with distance + bearing computed relative to a configured mine
centroid.

INE publishes shapefiles + CSVs of `localidades poblacionales` and
`manzanas censales`. The orchestrator handles the GIS conversion
(shapefile -> JSON), and this connector parses the simplified JSON.

Expected payload shape:

    {
      "places": [
        {
          "name": "Cuncumén",
          "kind": "town",
          "longitude": -70.701,
          "latitude": -31.971,
          "population": 600
        },
        ...
      ]
    }

Realtime semantics: this is **static spatial data**, not a time series.
There is no "realtime vs reanalysis" distinction; populated-place
geometries are census-cycle (5–10 yr) snapshots and are not consumed
as features by the realtime forecaster. The anti-hindsight protocol
treats static spatial data as out-of-scope (regulator-cycle reference
layer).
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from app.ingestion.public import cache as ingest_cache

SOURCE_NAME = "ine"

EARTH_RADIUS_M = 6_371_000.0
ALLOWED_KINDS = {
    "town",
    "school",
    "hospital",
    "drinking_water_intake",
    "indigenous_community",
    "protected_area",
    "other",
}


def _haversine_m(
    lon1: float, lat1: float, lon2: float, lat2: float
) -> float:
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def _bearing_deg(
    lon1: float, lat1: float, lon2: float, lat2: float
) -> float:
    """Initial bearing FROM (lon1,lat1) TO (lon2,lat2), degrees from north."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dlam = math.radians(lon2 - lon1)
    y = math.sin(dlam) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlam)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def parse_ine_payload(
    payload: Mapping[str, Any],
    *,
    mine_id: str,
    mine_lon: float,
    mine_lat: float,
) -> list[Mapping[str, Any]]:
    raw = payload.get("places")
    if not isinstance(raw, list):
        return []

    out: list[Mapping[str, Any]] = []
    for idx, p in enumerate(raw):
        if not isinstance(p, Mapping):
            continue
        lon = p.get("longitude")
        lat = p.get("latitude")
        name = p.get("name")
        if (
            not isinstance(lon, int | float)
            or not isinstance(lat, int | float)
            or isinstance(lon, bool)
            or isinstance(lat, bool)
            or not isinstance(name, str)
        ):
            continue
        kind_raw = p.get("kind", "town")
        kind = kind_raw if kind_raw in ALLOWED_KINDS else "other"
        place_id = str(p.get("place_id") or f"{mine_id}-place-{idx}")
        population = p.get("population")
        if population is not None and (
            not isinstance(population, int) or isinstance(population, bool) or population < 0
        ):
            population = None
        record: dict[str, Any] = {
            "place_id": place_id,
            "mine_id": mine_id,
            "name": name,
            "kind": kind,
            "longitude": float(lon),
            "latitude": float(lat),
            "population": population,
            "distance_to_mine_m": _haversine_m(
                mine_lon, mine_lat, float(lon), float(lat)
            ),
            "bearing_from_mine_deg": _bearing_deg(
                mine_lon, mine_lat, float(lon), float(lat)
            ),
            "source": SOURCE_NAME,
            "source_url": p.get("source_url"),
            "notes": p.get("notes"),
        }
        out.append(record)
    return out


class INEConnector:
    source_name = SOURCE_NAME

    def __init__(self, *, cache_dir: Path) -> None:
        self.cache_dir = cache_dir

    def fetch_from_payload(
        self,
        *,
        payload: Mapping[str, Any],
        mine_id: str,
        mine_lon: float,
        mine_lat: float,
    ) -> Iterable[Mapping[str, Any]]:
        return iter(
            parse_ine_payload(
                payload, mine_id=mine_id, mine_lon=mine_lon, mine_lat=mine_lat
            )
        )

    def fetch(
        self,
        *,
        window_from: datetime,
        window_to: datetime,
        **filters: object,
    ) -> Iterable[Mapping[str, Any]]:
        mine_id = filters.get("mine_id")
        mine_lon = filters.get("mine_lon")
        mine_lat = filters.get("mine_lat")
        if not isinstance(mine_id, str):
            raise TypeError("mine_id kwarg required")
        if not isinstance(mine_lon, int | float) or not isinstance(
            mine_lat, int | float
        ):
            raise TypeError("mine_lon/mine_lat kwargs required")
        cached = ingest_cache.get(
            source=SOURCE_NAME,
            window_from=window_from,
            window_to=window_to,
            filters={"mine_id": mine_id},
            cache_dir=self.cache_dir,
        )
        if cached is None:
            return iter(())
        return self.fetch_from_payload(
            payload=cached,
            mine_id=mine_id,
            mine_lon=float(mine_lon),
            mine_lat=float(mine_lat),
        )


__all__ = [
    "SOURCE_NAME",
    "INEConnector",
    "parse_ine_payload",
]
