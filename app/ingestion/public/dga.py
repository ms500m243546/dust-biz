"""DGA hydromet connector (Phase L.3).

Dirección General de Aguas (Chile) operates a national network of
meteorological + hydrological stations. The DGA portal exposes a JSON
endpoint per station that returns daily + hourly observations.

DGA station shape (simplified):

    {
      "station_code": "CUNCUMEN_DGA",
      "observations": [
        {
          "timestamp": "2026-05-01T03:00",
          "wind_speed_ms": 4.1,
          "wind_direction_deg": 220,
          "temperature_c": 12.4,
          "rainfall_mm": 0.0
        },
        ...
      ]
    }

DGA stations are valley-floor instruments — useful for Los Pelambres
receptor exposure (Cuncumén / Salamanca) but not for high-altitude
operating zones (Los Bronces). Pair with ERA5.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from app.ingestion.public import cache as ingest_cache

SOURCE_NAME = "dga"


def parse_dga_payload(
    payload: Mapping[str, Any],
    *,
    zone_id: str | None = None,
) -> list[Mapping[str, Any]]:
    observations = payload.get("observations")
    if not isinstance(observations, list):
        return []

    station_code = str(payload.get("station_code", "")) or None

    out: list[Mapping[str, Any]] = []
    for obs in observations:
        if not isinstance(obs, Mapping):
            continue
        ts_raw = obs.get("timestamp")
        if not isinstance(ts_raw, str):
            continue
        try:
            ts = datetime.fromisoformat(ts_raw)
        except ValueError:
            continue
        record: dict[str, Any] = {
            "source": SOURCE_NAME,
            "timestamp": ts,
            "zone_id": zone_id,
            "station_code": station_code,
        }
        for key in (
            "wind_speed_ms",
            "wind_direction_deg",
            "gust_speed_ms",
            "humidity_pct",
            "temperature_c",
            "pressure_hpa",
            "solar_wm2",
        ):
            v = obs.get(key)
            if v is None:
                record[key] = None
            elif isinstance(v, int | float) and not isinstance(v, bool):
                record[key] = float(v)
        # DGA reports rainfall as mm per hour or mm per day depending on
        # station; we land it in `rainfall_mm_15min` and trust the caller
        # to know the temporal resolution. The station registry tracks
        # per-station resolution.
        rain = obs.get("rainfall_mm")
        if rain is not None and isinstance(rain, int | float) and not isinstance(rain, bool):
            record["rainfall_mm_15min"] = float(rain)
        out.append(record)
    return out


class DGAConnector:
    source_name = SOURCE_NAME

    def __init__(self, *, cache_dir: Path) -> None:
        self.cache_dir = cache_dir

    def fetch_from_payload(
        self,
        *,
        payload: Mapping[str, Any],
        zone_id: str | None = None,
    ) -> Iterable[Mapping[str, Any]]:
        return iter(parse_dga_payload(payload, zone_id=zone_id))

    def fetch(
        self,
        *,
        window_from: datetime,
        window_to: datetime,
        **filters: object,
    ) -> Iterable[Mapping[str, Any]]:
        station_code = filters.get("station_code")
        if not isinstance(station_code, str):
            raise TypeError("station_code kwarg is required")
        zone_id = filters.get("zone_id")
        if zone_id is not None and not isinstance(zone_id, str):
            raise TypeError("zone_id must be str if provided")
        cached = ingest_cache.get(
            source=SOURCE_NAME,
            window_from=window_from,
            window_to=window_to,
            filters={"station_code": station_code},
            cache_dir=self.cache_dir,
        )
        if cached is None:
            return iter(())
        return self.fetch_from_payload(payload=cached, zone_id=zone_id)


__all__ = [
    "SOURCE_NAME",
    "DGAConnector",
    "parse_dga_payload",
]
