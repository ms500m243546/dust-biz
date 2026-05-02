"""Open-Meteo connector (Phase L.3).

Free global weather (historical + forecast) with no API key. Used as
a development / prototyping fallback. **Production deployments must
swap to ERA5** because Open-Meteo's CC-BY-NC license forbids
commercial use; see docs/data-source-registry.md license table.

Open-Meteo's JSON shape (historical archive endpoint) is:

    {
      "latitude": ...,
      "longitude": ...,
      "hourly": {
        "time": ["2026-05-01T00:00", ...],
        "temperature_2m": [12.3, ...],
        "wind_speed_10m": [4.5, ...],
        "wind_direction_10m": [220, ...],
        ...
      }
    }

The connector parses arrays into per-timestamp `RawWeatherReading`-shaped
dicts. Missing variables surface as None (the schema accepts None).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from app.ingestion.public import cache as ingest_cache

SOURCE_NAME = "open_meteo"


_VARIABLE_MAP: dict[str, str] = {
    # Open-Meteo key -> our schema key
    "temperature_2m": "temperature_c",
    "wind_speed_10m": "wind_speed_ms",
    "wind_direction_10m": "wind_direction_deg",
    "wind_gusts_10m": "gust_speed_ms",
    "relative_humidity_2m": "humidity_pct",
    "surface_pressure": "pressure_hpa",
    "rain": "rainfall_mm_15min",  # 15-min aggregation handled by caller
    "shortwave_radiation": "solar_wm2",
}


def parse_open_meteo_payload(
    payload: Mapping[str, Any],
    *,
    zone_id: str | None = None,
) -> list[Mapping[str, Any]]:
    """Convert Open-Meteo JSON into a list of RawWeatherReading-shaped dicts.

    Wind speed comes back in m/s when `wind_speed_unit=ms` is set on
    the request; we pass that through unchanged. Temperature is in °C
    when `temperature_unit=celsius`. The caller is responsible for
    requesting the right units; this parser does not convert.
    """
    hourly = payload.get("hourly")
    if not isinstance(hourly, Mapping):
        return []
    time_arr = hourly.get("time")
    if not isinstance(time_arr, list):
        return []

    out: list[Mapping[str, Any]] = []
    for idx, t_str in enumerate(time_arr):
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
        for om_key, schema_key in _VARIABLE_MAP.items():
            arr = hourly.get(om_key)
            if not isinstance(arr, list) or idx >= len(arr):
                continue
            v = arr[idx]
            if v is None:
                record[schema_key] = None
                continue
            if isinstance(v, int | float) and not isinstance(v, bool):
                record[schema_key] = float(v)
        out.append(record)
    return out


class OpenMeteoConnector:
    source_name = SOURCE_NAME

    def __init__(self, *, cache_dir: Path) -> None:
        self.cache_dir = cache_dir

    def fetch_from_payload(
        self,
        *,
        payload: Mapping[str, Any],
        zone_id: str | None = None,
    ) -> Iterable[Mapping[str, Any]]:
        return iter(parse_open_meteo_payload(payload, zone_id=zone_id))

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
    "OpenMeteoConnector",
    "parse_open_meteo_payload",
]
