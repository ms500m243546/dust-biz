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
    """Parse a SINCA `tsindico2.cgi?outtype=xcl` export into raw_value dicts.

    The real SINCA hourly + daily export schema (verified empirically
    against Cuncumén station 424 across a 12-month window in May 2026)
    is six semicolon-separated columns with only the first two labeled
    in the header row:

        FECHA (YYMMDD);HORA (HHMM);
        260425;0100;;24;;            <- recent: validated value at col 3
        260425;0400;;;0;             <- raw fallback at col 4
        250521;2000;23;;;            <- older: pre-validated value at col 2

    Column semantics (inferred from QA-pipeline behavior):

        col 0  FECHA  YYMMDD
        col 1  HORA   HHMM (0000 for daily-resolution exports)
        col 2  pre-validated value — the operator's reading before
               SMA/MMA QA. Populated for the most-recent ~year of
               history; cleared once a row is promoted to col 3.
        col 3  validated value — the regulator-blessed number. Lags
               col 2 by ~1 week while QA runs.
        col 4  raw/non-validated fallback — surfaces when neither
               col 2 nor col 3 carries a value (typical of indicative
               networks or rejected QA).
        col 5  trailing empty padding from the gateway

    Value priority: col 3 (validated) → col 2 (pre-validated) → col 4
    (raw). The `validated` flag is True only when the value sourced
    from col 3.
    """
    out: list[Mapping[str, Any]] = []
    reader = csv.reader(io.StringIO(payload), delimiter=";")
    rows = list(reader)
    if not rows:
        return out
    # First row is header; skip it.
    for row in rows[1:]:
        if len(row) < 5:
            continue
        date_yymmdd = row[0].strip()
        time_hhmm = row[1].strip()
        if not date_yymmdd or not time_hhmm:
            continue
        try:
            ts = datetime.strptime(f"{date_yymmdd} {time_hhmm.zfill(4)}", "%y%m%d %H%M")
        except ValueError:
            continue
        prelim_raw = row[2].strip().replace(",", ".") if len(row) > 2 else ""
        validated_raw = row[3].strip().replace(",", ".") if len(row) > 3 else ""
        fallback_raw = row[4].strip().replace(",", ".") if len(row) > 4 else ""
        if validated_raw not in ("", "S/I", "NA", "n/a"):
            value_str, validated = validated_raw, True
        elif prelim_raw not in ("", "S/I", "NA", "n/a"):
            value_str, validated = prelim_raw, False
        elif fallback_raw not in ("", "S/I", "NA", "n/a"):
            value_str, validated = fallback_raw, False
        else:
            continue
        try:
            value = float(value_str)
        except ValueError:
            continue
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
    region_path: str = "RM",
    resolution: str = "horario",
) -> str:
    """Build the SINCA `tsindico2.cgi` Excel-export URL.

    Verified empirically against the live portal (Cuncumén station 424
    in Coquimbo / RIV) on 2026-05-02. The macro structure is:

        ./<region_path>/<station_code>/Cal/<PARAM>/<PARAM>.<res>.<res>.ic

    Date format is YYMMDDHH — `from` is anchored to hour 00, `to` to
    hour 23 of each calendar day. `region_path` follows SINCA's
    internal taxonomy (RM, RIV, RV, ...); `resolution` is one of
    "horario" (hourly) or "diario" (daily).
    """
    code = _PARAM_CODES.get(parameter)
    if code is None:
        raise ValueError(f"unsupported SINCA parameter: {parameter}")
    macro = f"./{region_path}/{station_code}/Cal/{code}/{code}.{resolution}.{resolution}.ic"
    qs = urllib.parse.urlencode(
        {
            "outtype": "xcl",
            "macro": macro,
            "from": window_from.strftime("%y%m%d") + "00",
            "to": window_to.strftime("%y%m%d") + "23",
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
