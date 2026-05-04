"""DMC (Dirección Meteorológica de Chile) connector — Phase BA.1.

Official Chilean meteorological service. DMC publishes hourly surface
observations from a national network of stations (https://climatologia.meteochile.gob.cl/).
For Los Pelambres / Choapa-basin coverage, DMC complements DGA
hydromet (which is denser in valleys but sparser at altitude) and
fills the gap that SINCA-empty stations leave.

Access pattern (matches the ERA5 / DGA convention):

* The official DMC API requires registration. To keep CI dependency-
  free and deterministic, this module ships a payload-mode parser
  only. An out-of-band orchestrator hits DMC, normalizes the
  per-station hourly response to the JSON shape below, and feeds it
  to `parse_dmc_payload`.
* Live mode (`fetch_live(...)`) is intentionally deferred until the
  CDS-API style live mode is wired for ERA5 (same pattern Phase L.M.2
  uses). A `NotImplementedError` here is the explicit deferral marker.

Payload shape (per request, one station at a time):

    {
      "station_code": "330020",
      "time": ["2026-05-01T00:00", "2026-05-01T01:00", ...],
      "temperature_c":   [12.3, 11.8, ...],
      "humidity_pct":    [55.0, 58.0, ...],
      "wind_speed_ms":   [3.2, 2.7, ...],
      "wind_direction_deg": [240.0, 245.0, ...],
      "pressure_hpa":    [882.0, 881.5, ...],
      "rainfall_mm_15min": [0.0, 0.0, ...]   # optional
    }

Output: a list of `RawWeatherReading`-shaped dicts ready for the
seed-mode orchestrator.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

SOURCE_NAME = "dmc"


def parse_dmc_payload(
    payload: Mapping[str, Any],
    *,
    weather_target_id: str,
) -> list[dict[str, Any]]:
    """Convert pre-extracted DMC JSON into RawWeatherReading-shaped dicts.

    `weather_target_id` is required so the consumer can attribute
    the readings to a `WeatherReading.weather_target_id` row without
    re-deriving it from station_code (the YAML drives that mapping).
    """
    times = payload.get("time")
    if not isinstance(times, list) or not times:
        return []

    rows: list[dict[str, Any]] = []
    for i, ts in enumerate(times):
        row: dict[str, Any] = {
            "source": SOURCE_NAME,
            "weather_target_id": weather_target_id,
            "timestamp": ts,
            "realtime_proxy": True,  # DMC publishes near-realtime; matches L.3 convention
            "raw_value": {},
        }
        for key in (
            "temperature_c",
            "humidity_pct",
            "wind_speed_ms",
            "wind_direction_deg",
            "pressure_hpa",
            "rainfall_mm_15min",
        ):
            series = payload.get(key)
            if isinstance(series, list) and i < len(series):
                value = series[i]
                if value is not None:
                    row[key] = float(value)
                    row["raw_value"][key] = value
        station_code = payload.get("station_code")
        if station_code is not None:
            row["raw_value"]["station_code"] = station_code
        rows.append(row)
    return rows


def fetch_live(*_: Any, **__: Any) -> list[dict[str, Any]]:
    """Live DMC API mode — deferred.

    The DMC public API requires registration + per-request keys. We
    keep the live-mode contract here so the orchestrator can call it
    once the auth path is wired (matches Phase L.M.2 ERA5 convention).
    Until then, callers must use the payload-mode parser fed by an
    out-of-band download.
    """
    raise NotImplementedError(
        "DMC live mode is deferred — use parse_dmc_payload(...) with a "
        "pre-extracted JSON payload until the live auth path is wired"
    )


__all__ = ["SOURCE_NAME", "fetch_live", "parse_dmc_payload"]
