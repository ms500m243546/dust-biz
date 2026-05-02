"""ERA5 reanalysis connector (Phase L.3).

Hourly atmospheric reanalysis from ECMWF / Copernicus Climate Data
Store (CDS). **Primary weather source** for high-altitude mines like
Los Bronces (3,500 m) where surface stations don't represent the
operating regime. Commercial-use OK with attribution
("Generated using Copernicus Climate Change Service information").

Access pattern:
- The CDS API requires a free account + a `~/.cdsapirc` file with the
  user's UID and API key. The actual download is handled by the
  `cdsapi` Python package and produces a NetCDF or GRIB file.
- This connector deliberately does NOT depend on `cdsapi` or `xarray`
  to keep the dependency footprint small in CI. Instead, the
  orchestrator script (run out-of-band) downloads the NetCDF, exports
  one hour-per-row JSON via `xarray.to_dict()`, and feeds the JSON to
  this parser.
- Tests use the captured JSON shape — no live CDS calls in CI.

ERA5 grid is 0.25° (~28km). For a single mine we sample the nearest
grid cell (handled by the orchestrator's pre-extract step) so the
parser sees one timeseries per request.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from app.ingestion.public import cache as ingest_cache

SOURCE_NAME = "era5"

# Map ERA5 short names (or our pre-extracted aliases) to schema keys.
_VARIABLE_MAP: dict[str, str] = {
    "u10": "_u10",  # eastward wind 10m, m/s — combined into wind_speed below
    "v10": "_v10",  # northward wind 10m, m/s
    "t2m": "temperature_c",  # already in °C after pre-extract conversion
    "sp": "pressure_hpa",  # surface pressure, hPa after pre-extract conversion
    "tp": "rainfall_mm_15min",  # total precipitation, mm/hr aggregated upstream
    "ssrd": "solar_wm2",  # surface solar radiation downwards
    "rh2m": "humidity_pct",  # derived from t2m + d2m by the pre-extract
}


def _wind_speed_dir(u: float | None, v: float | None) -> tuple[float | None, float | None]:
    """Return (speed_ms, dir_deg_from). dir is meteorological (where wind comes from)."""
    if u is None or v is None:
        return None, None
    speed = (u * u + v * v) ** 0.5
    # ERA5 u/v are in the eastward/northward direction the wind blows toward.
    # Meteorological "from" direction = atan2(-u, -v) in degrees from north.
    import math

    dir_to = math.degrees(math.atan2(u, v))  # direction wind is going to
    dir_from = (dir_to + 180.0) % 360.0
    return speed, dir_from


def parse_era5_payload(
    payload: Mapping[str, Any],
    *,
    zone_id: str | None = None,
) -> list[Mapping[str, Any]]:
    """Convert pre-extracted ERA5 JSON into RawWeatherReading-shaped dicts.

    Expected payload shape:

        {
          "time": ["2026-05-01T00:00", ...],
          "u10":  [3.4, ...],
          "v10":  [-1.2, ...],
          "t2m":  [12.3, ...],
          ...
        }
    """
    times = payload.get("time")
    if not isinstance(times, list):
        return []

    out: list[Mapping[str, Any]] = []
    for idx, t_str in enumerate(times):
        if not isinstance(t_str, str):
            continue
        try:
            ts = datetime.fromisoformat(t_str)
        except ValueError:
            continue

        record: dict[str, Any] = {
            "source": SOURCE_NAME,
            "timestamp": ts,
            "zone_id": zone_id,
        }
        for era_key, schema_key in _VARIABLE_MAP.items():
            arr = payload.get(era_key)
            if not isinstance(arr, list) or idx >= len(arr):
                continue
            v = arr[idx]
            if v is None or not isinstance(v, int | float) or isinstance(v, bool):
                if not schema_key.startswith("_"):
                    record[schema_key] = None
                continue
            if not schema_key.startswith("_"):
                record[schema_key] = float(v)
            else:
                record[schema_key] = float(v)

        u = record.pop("_u10", None)
        v = record.pop("_v10", None)
        speed, direction = _wind_speed_dir(u, v)
        record["wind_speed_ms"] = speed
        record["wind_direction_deg"] = direction
        out.append(record)
    return out


class ERA5Connector:
    source_name = SOURCE_NAME

    def __init__(self, *, cache_dir: Path) -> None:
        self.cache_dir = cache_dir

    def fetch_from_payload(
        self,
        *,
        payload: Mapping[str, Any],
        zone_id: str | None = None,
    ) -> Iterable[Mapping[str, Any]]:
        return iter(parse_era5_payload(payload, zone_id=zone_id))

    def fetch(
        self,
        *,
        window_from: datetime,
        window_to: datetime,
        **filters: object,
    ) -> Iterable[Mapping[str, Any]]:
        latitude = filters.get("latitude")
        longitude = filters.get("longitude")
        if not isinstance(latitude, int | float) or not isinstance(
            longitude, int | float
        ):
            raise TypeError("latitude/longitude kwargs are required")
        zone_id = filters.get("zone_id")
        if zone_id is not None and not isinstance(zone_id, str):
            raise TypeError("zone_id must be str if provided")
        cached = ingest_cache.get(
            source=SOURCE_NAME,
            window_from=window_from,
            window_to=window_to,
            filters={"latitude": float(latitude), "longitude": float(longitude)},
            cache_dir=self.cache_dir,
        )
        if cached is None:
            return iter(())
        return self.fetch_from_payload(payload=cached, zone_id=zone_id)


__all__ = [
    "SOURCE_NAME",
    "ERA5Connector",
    "parse_era5_payload",
]
