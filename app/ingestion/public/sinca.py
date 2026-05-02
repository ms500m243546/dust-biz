"""SINCA connector (Phase L.2).

Fetches PM10 / PM2.5 hourly readings from Chile's Sistema de
Información Nacional de Calidad del Aire (sinca.mma.gob.cl).

The SINCA portal exposes per-station CSV downloads via a public
gateway (no API key, but rate-limited by IP). Each request targets
one station + one parameter + one time range; the connector chunks
multi-station fetches and applies disk caching.

Quality hint: SINCA stations operated under D.S. 61/2008
EMRPM/EMRP standards are regulator-grade reference monitors. This
connector tags them at `source_quality_hint=0.9`. Stations marked
`indicative` (lower-spec) get 0.7 — empirically derived; the K.1
model performance scoreboard will calibrate this over time.

This module is a pure parser + fetcher; persistence is the
orchestrator's job. Tests use captured CSV fixtures (no live
network in CI).
"""

from __future__ import annotations

import csv
import io
import urllib.parse
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app.ingestion.public import cache as ingest_cache

SOURCE_NAME = "sinca"
_BASE = "https://sinca.mma.gob.cl/cgi-bin/APUB-MMA/apub.tsindico2.cgi"

# Parameter codes used by SINCA's CSV export endpoint.
_PARAM_CODES = {
    "pm10": "PM10",
    "pm25": "PM2.5",
}

_REGULATOR_GRADE_TIER = "EMRPM"  # estación de monitoreo de referencia
_INDICATIVE_TIER = "indicative"


@dataclass(frozen=True)
class SincaStation:
    """A SINCA station record loaded from the registry-extract fixture."""

    station_code: str
    station_name: str
    region: str
    commune: str
    longitude: float
    latitude: float
    tier: str  # "EMRPM" | "indicative"
    parameters: tuple[str, ...]  # subset of {"pm10","pm25",...}


def quality_hint_for_tier(tier: str) -> float:
    """Map SINCA station tier to source_quality_hint."""
    if tier == _REGULATOR_GRADE_TIER:
        return 0.9
    if tier == _INDICATIVE_TIER:
        return 0.7
    return 0.5


def parse_sinca_csv(payload: str, *, station_code: str, parameter: str) -> list[Mapping[str, Any]]:
    """Parse a SINCA CSV export into raw_value dicts.

    SINCA's CSV format (simplified for the fields we use):
        FECHA (YYYY-MM-DD HH:MM); VALOR; VALIDADO

    Rows with non-numeric VALOR (header / NA / "S/I" sin información)
    are dropped silently. Validated-only filtering is the caller's job;
    we surface every row with the `validated` flag preserved.
    """
    out: list[Mapping[str, Any]] = []
    reader = csv.DictReader(io.StringIO(payload), delimiter=";")
    column_value = _detect_value_column(list(reader.fieldnames or []), parameter)
    if column_value is None:
        return out
    for row in reader:
        ts_raw = (row.get("FECHA") or row.get("fecha") or "").strip()
        if not ts_raw:
            continue
        try:
            ts = datetime.strptime(ts_raw, "%Y-%m-%d %H:%M")
        except ValueError:
            try:
                ts = datetime.fromisoformat(ts_raw)
            except ValueError:
                continue
        value_raw = (row.get(column_value) or "").replace(",", ".").strip()
        if value_raw in ("", "S/I", "NA", "n/a"):
            continue
        try:
            value = float(value_raw)
        except ValueError:
            continue
        validated_field = (row.get("VALIDADO") or row.get("validado") or "").strip().lower()
        validated = validated_field in {"1", "true", "si", "sí", "v"}
        out.append(
            {
                "station_code": station_code,
                "timestamp": ts,
                "parameter": parameter,
                "value_ugm3": value,
                "validated": validated,
            }
        )
    return out


def _detect_value_column(fieldnames: list[str], parameter: str) -> str | None:
    target = parameter.upper()
    for name in fieldnames:
        if name.upper().startswith("VALOR") or name.upper() == target:
            return name
    # Some exports use the parameter code directly as the column.
    code = _PARAM_CODES.get(parameter)
    if code and code in fieldnames:
        return code
    return None


def to_raw_sensor_payload(
    record: Mapping[str, Any],
    *,
    station: SincaStation,
) -> dict[str, Any]:
    """Build the `raw_value` dict for one parsed SINCA row.

    The returned dict is what gets stored in
    `SensorReading.raw_value`. The orchestrator wraps it with the
    `sensor_id`, `timestamp`, and `source_quality_hint` columns.
    """
    parameter = str(record["parameter"])
    pm_key = f"{parameter}_ugm3"  # pm10_ugm3 / pm25_ugm3 — matches K.2 reports.py
    return {
        "source": SOURCE_NAME,
        "station_code": station.station_code,
        "station_name": station.station_name,
        "region": station.region,
        "commune": station.commune,
        "tier": station.tier,
        "parameter": parameter,
        "validated": bool(record.get("validated", False)),
        pm_key: record["value_ugm3"],
    }


def build_url(
    *,
    station_code: str,
    parameter: str,
    window_from: datetime,
    window_to: datetime,
) -> str:
    """Build the SINCA CSV download URL for one (station, parameter, window).

    SINCA uses a query-string format with date keys `from` / `to` in
    YYYYMMDD and a parameter code; this function captures the gateway
    pattern in one place so the live-fetch path is testable in
    isolation (the parser doesn't care how the URL is built).
    """
    code = _PARAM_CODES.get(parameter)
    if code is None:
        raise ValueError(f"unsupported SINCA parameter: {parameter}")
    qs = urllib.parse.urlencode(
        {
            "outtype": "xcl",  # CSV-style export
            "macro": "./RM/" + station_code + "/Cal/" + code,
            "from": window_from.strftime("%Y%m%d"),
            "to": window_to.strftime("%Y%m%d"),
        }
    )
    return f"{_BASE}?{qs}"


class SincaConnector:
    """Pure fetcher — caller is responsible for HTTP + persistence.

    The recommended runtime layout is for the orchestrator script to
    `import requests`, hit `build_url(...)`, cache via
    `app.ingestion.public.cache`, and feed the body to
    `parse_sinca_csv(...)`. Tests skip the HTTP step entirely by
    feeding a captured fixture into `parse_sinca_csv` directly.
    """

    source_name = SOURCE_NAME

    def __init__(self, *, cache_dir: Path) -> None:
        self.cache_dir = cache_dir

    def fetch_from_payload(
        self,
        *,
        station: SincaStation,
        parameter: str,
        payload: str,
    ) -> Iterable[Mapping[str, Any]]:
        """Parse a CSV body in-memory; useful for tests + offline runs."""
        for rec in parse_sinca_csv(
            payload, station_code=station.station_code, parameter=parameter
        ):
            yield to_raw_sensor_payload(rec, station=station)

    def fetch(
        self,
        *,
        window_from: datetime,
        window_to: datetime,
        **filters: object,
    ) -> Iterable[Mapping[str, Any]]:
        """Live fetch path.

        Reads the CSV from the disk cache if available; else returns an
        empty iterable. Live HTTP is intentionally NOT performed inside
        this method — see the module docstring. Wire it from the
        orchestrator at runtime so tests stay deterministic.
        """
        station = filters.get("station")
        parameter = filters.get("parameter")
        if not isinstance(station, SincaStation):
            raise TypeError("station kwarg must be a SincaStation")
        if not isinstance(parameter, str):
            raise TypeError("parameter kwarg must be a str")
        cached = ingest_cache.get(
            source=SOURCE_NAME,
            window_from=window_from,
            window_to=window_to,
            filters={"station_code": station.station_code, "parameter": parameter},
            cache_dir=self.cache_dir,
        )
        if cached is None:
            return iter(())
        # Cache stores the raw CSV string under "csv".
        body = str(cached.get("csv", ""))
        return self.fetch_from_payload(
            station=station, parameter=parameter, payload=body
        )


__all__ = [
    "SOURCE_NAME",
    "SincaConnector",
    "SincaStation",
    "build_url",
    "parse_sinca_csv",
    "quality_hint_for_tier",
    "to_raw_sensor_payload",
]
