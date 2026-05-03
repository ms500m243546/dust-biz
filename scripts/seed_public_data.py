"""Public-data ingest orchestrator (Phases L.7b + L.M.1).

Wires the public-source connectors (SINCA, Open-Meteo, ERA5) to
live HTTP using stdlib `urllib.request` (no new dependency), the
disk cache in `app/ingestion/public/cache.py`, and the existing
repositories for persistence.

Usage:

    # Wire-only sanity check, no network. Reads from data_cache/ if a
    # prior run populated it; exits 0 with a count of records written.
    python scripts/seed_public_data.py --source sinca --dry-run

    # SINCA live pull. The user runs this themselves; it hits SINCA's
    # CSV gateway, writes the body to data_cache/sinca/, parses, and
    # persists into the dev SQLite DB.
    python scripts/seed_public_data.py --source sinca \\
        --station 424 --parameter pm10 --region-path RIV \\
        --from 2026-04-25 --to 2026-05-01 \\
        --mine-id los-pelambres --sensor-id lp-em05-cuncumen

    # SINCA YAML batch (multi-station from RCA seed):
    python scripts/seed_public_data.py --source sinca \\
        --from-yaml data_seed/los_pelambres.yaml \\
        --from 2025-05-01 --to 2026-05-02

    # Open-Meteo live pull at a single point (CC-BY-NC; dev only):
    python scripts/seed_public_data.py --source open_meteo \\
        --latitude -31.971 --longitude -70.701 --zone-id lp-cuncumen-met \\
        --from 2025-05-01 --to 2026-05-02

    # Open-Meteo YAML batch (one request per `weather_targets:` entry):
    python scripts/seed_public_data.py --source open_meteo \\
        --from-yaml data_seed/los_pelambres.yaml \\
        --from 2025-05-01 --to 2026-05-02

    # ERA5 stub mode: feeds a pre-extracted JSON payload through the
    # parser. Full CDS-API integration deferred to L.M.2.
    python scripts/seed_public_data.py --source era5 \\
        --era5-payload era5_cuncumen_2025_2026.json \\
        --zone-id lp-cuncumen-met

The orchestrator is intentionally explicit about which station/point,
which parameter, which window, and which sensor or zone receives the
ingest. No magic discovery — calibration drift is too costly.

Tests cover the parsing path (fixture replay) — the live HTTP path
is exercised by the operator when running this script.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.ingestion.public import cache as ingest_cache  # noqa: E402,I001
from app.ingestion.public.era5 import (  # noqa: E402,I001
    SOURCE_NAME as ERA5_SOURCE,
    parse_era5_payload,
)
from app.ingestion.public.open_meteo import (  # noqa: E402,I001
    LICENSE_NOTE as OPEN_METEO_LICENSE_NOTE,
    SOURCE_NAME as OPEN_METEO_SOURCE,
    build_url as build_open_meteo_url,
    parse_open_meteo_payload,
)
from app.ingestion.public.sinca import (  # noqa: E402,I001
    SOURCE_NAME as SINCA_SOURCE,
    SincaConnector,
    SincaStation,
    build_url,
    expand_to_pit_records,
    parse_sinca_csv,
    quality_hint_for_tier,
    to_raw_sensor_payload,
)
from app.storage.database import get_engine, session_scope  # noqa: E402,I001
from app.storage.models import Base, SensorReading, WeatherReading  # noqa: E402,I001


def _parse_date(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d")


def _http_get(url: str, *, timeout_seconds: float = 30.0) -> str:
    """Fetch a URL with a polite User-Agent. stdlib only."""
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "DustOps-AI/0.1 (research; contact: ignacio@dustops.ai)"
        },
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as resp:
        body: bytes = resp.read()
        # SINCA returns Latin-1 / Windows-1252 in some endpoints; try
        # UTF-8 first then fall back.
        try:
            return body.decode("utf-8")
        except UnicodeDecodeError:
            return body.decode("latin-1")


def _persist_sinca(
    *,
    station: SincaStation,
    parameter: str,
    csv_body: str,
    sensor_id: str,
) -> int:
    """Parse a SINCA CSV body and persist as PIT-aware SensorReading rows.

    M.2: emits both pre-validated (col 2) and validated (col 3)
    versions when both are present in the CSV; pairs each with its
    PIT validity interval via `expand_to_pit_records`. Idempotent:
    re-runs on the same window are a no-op (SQLite `INSERT OR IGNORE`
    against the unique constraint `(sensor_id, timestamp, valid_from)`).
    """
    parsed = parse_sinca_csv(
        csv_body,
        station_code=station.station_code,
        parameter=parameter,
        emit_all_versions=True,
    )
    pit_rows = expand_to_pit_records(parsed)
    quality_hint = quality_hint_for_tier(station.tier)
    Base.metadata.create_all(get_engine())
    written = 0
    skipped = 0
    with session_scope() as session:
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        for rec in pit_rows:
            raw_value = to_raw_sensor_payload(rec, station=station)
            stmt = (
                sqlite_insert(SensorReading)
                .values(
                    sensor_id=sensor_id,
                    timestamp=rec["timestamp"],
                    raw_value=raw_value,
                    source_quality_hint=quality_hint,
                    valid_from=rec["valid_from"],
                    valid_to=rec["valid_to"],
                    pit_version="v1",
                )
                .prefix_with("OR IGNORE")
            )
            result = session.execute(stmt)
            # rowcount is 1 on insert, 0 on conflict-ignore.
            rowcount: int = getattr(result, "rowcount", 0) or 0
            if rowcount > 0:
                written += 1
            else:
                skipped += 1
    if skipped:
        print(f"  sinca persist: {skipped} duplicate row(s) skipped (idempotent)")
    return written


def _run_one_sinca(
    *,
    station: SincaStation,
    parameter: str,
    region_path: str,
    window_from: datetime,
    window_to: datetime,
    cache_dir: Path,
    dry_run: bool,
    no_persist: bool,
    sensor_id: str | None,
    resolution: str = "horario",
) -> dict[str, Any]:
    """Execute one (station, parameter, window) pull. Returns a status dict.

    Used both by the single-station CLI mode (`--station ...`) and the
    YAML batch mode (`--from-yaml ...`). Per-station HTTP failures
    return a structured result rather than raising — the YAML driver
    needs to continue past individual outages.
    """
    cache_filters = {
        "station_code": station.station_code,
        "parameter": parameter,
        "resolution": resolution,
    }
    cached = ingest_cache.get(
        source=SINCA_SOURCE,
        window_from=window_from,
        window_to=window_to,
        filters=cache_filters,
        cache_dir=cache_dir,
    )

    if cached is not None:
        body = str(cached.get("csv", ""))
        source_tag = "cache"
    elif dry_run:
        return {
            "station_code": station.station_code,
            "status": "dry-run-no-cache",
            "records": 0,
            "written": 0,
        }
    else:
        url = build_url(
            station_code=station.station_code,
            parameter=parameter,
            window_from=window_from,
            window_to=window_to,
            region_path=region_path,
            resolution=resolution,
        )
        try:
            body = _http_get(url)
        except urllib.error.URLError as exc:
            return {
                "station_code": station.station_code,
                "status": "http-error",
                "error": str(exc),
                "records": 0,
                "written": 0,
            }
        ingest_cache.put(
            payload={"csv": body, "url": url},
            source=SINCA_SOURCE,
            window_from=window_from,
            window_to=window_to,
            filters=cache_filters,
            cache_dir=cache_dir,
        )
        source_tag = "live"

    conn = SincaConnector(cache_dir=cache_dir)
    parsed = list(
        conn.fetch_from_payload(
            station=station, parameter=parameter, payload=body
        )
    )
    if no_persist or not sensor_id:
        return {
            "station_code": station.station_code,
            "status": f"{source_tag}-parsed",
            "records": len(parsed),
            "written": 0,
            "bytes": len(body),
        }
    written = _persist_sinca(
        station=station,
        parameter=parameter,
        csv_body=body,
        sensor_id=sensor_id,
    )
    return {
        "station_code": station.station_code,
        "status": f"{source_tag}-persisted",
        "records": len(parsed),
        "written": written,
        "bytes": len(body),
        "sensor_id": sensor_id,
    }


def cmd_sinca(args: argparse.Namespace) -> int:
    cache_dir = Path(args.cache_dir)
    station = SincaStation(
        station_code=args.station,
        station_name=args.station_name or args.station,
        region=args.region or "",
        commune=args.commune or "",
        longitude=args.longitude or 0.0,
        latitude=args.latitude or 0.0,
        tier=args.tier,
        parameters=(args.parameter,),
    )
    window_from = _parse_date(args.window_from)
    window_to = _parse_date(args.window_to)
    result = _run_one_sinca(
        station=station,
        parameter=args.parameter,
        region_path=args.region_path,
        window_from=window_from,
        window_to=window_to,
        cache_dir=cache_dir,
        dry_run=args.dry_run,
        no_persist=args.no_persist,
        sensor_id=args.sensor_id,
        resolution=args.resolution,
    )
    status = result["status"]
    if status == "dry-run-no-cache":
        print("dry-run: no cache entry and live fetch disabled; exiting 0")
        return 0
    if status == "http-error":
        print(f"http error: {result['error']}", file=sys.stderr)
        return 2
    if status.endswith("-parsed"):
        if status.startswith("cache"):
            print(f"cache hit: {result['bytes']} chars from {cache_dir}")
        else:
            print(f"cached {result['bytes']} chars to {cache_dir}")
        print(f"parsed {result['records']} records (no-persist mode)")
        return 0
    if status.endswith("-persisted"):
        if status.startswith("live"):
            print(f"cached {result['bytes']} chars to {cache_dir}")
        print(
            f"wrote {result['written']} SensorReading rows for "
            f"sensor_id={result['sensor_id']}"
        )
        return 0
    if not args.sensor_id and not args.no_persist:
        print("--sensor-id required when persisting", file=sys.stderr)
        return 2
    return 0


def cmd_sinca_from_yaml(args: argparse.Namespace) -> int:
    """Drive a SINCA batch pull from an RCA-seed YAML file.

    Reads the `sensors:` list from the YAML. For each sensor with
    a non-null `sinca_station_code`, fans out one HTTP request and
    accumulates a per-station summary. Continues past individual
    failures so partial outages don't block the whole batch.
    """
    cache_dir = Path(args.cache_dir)
    window_from = _parse_date(args.window_from)
    window_to = _parse_date(args.window_to)
    yaml_path = Path(args.from_yaml)
    doc = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    sensors = doc.get("sensors") or []

    def _eligible(s: dict[str, Any]) -> bool:
        if not s.get("sinca_station_code"):
            return False
        # Allow override; default to skipping known-empty stations.
        status = s.get("sinca_data_status", "has_data")
        return not (status == "no_published_data" and not args.include_empty)

    eligible = [s for s in sensors if _eligible(s)]
    print(
        f"yaml: {len(sensors)} sensor(s), {len(eligible)} eligible for SINCA pull"
    )
    skipped_private = [s for s in sensors if not s.get("sinca_station_code")]
    if skipped_private:
        print(
            "  skipping operator-private (no sinca_station_code): "
            + ", ".join(s["sensor_id"] for s in skipped_private)
        )
    skipped_empty = [
        s for s in sensors
        if s.get("sinca_station_code")
        and s.get("sinca_data_status") == "no_published_data"
        and not args.include_empty
    ]
    if skipped_empty:
        print(
            "  skipping no_published_data (use --include-empty to override): "
            + ", ".join(s["sensor_id"] for s in skipped_empty)
        )

    results: list[dict[str, Any]] = []
    for spec in eligible:
        sensor_id = spec["sensor_id"]
        sinca_code = str(spec["sinca_station_code"])
        region_path = spec.get("sinca_region_path") or args.region_path
        resolution = spec.get("sinca_resolution") or "horario"
        sensor_type = spec.get("sensor_type", "pm10")
        if sensor_type not in ("pm10", "pm25"):
            print(f"  {sensor_id}: skipped (unsupported sensor_type {sensor_type!r})")
            continue
        station = SincaStation(
            station_code=sinca_code,
            station_name=sensor_id,
            region=region_path,
            commune="",
            longitude=0.0,
            latitude=0.0,
            tier=args.tier,
            parameters=(sensor_type,),
        )
        result = _run_one_sinca(
            station=station,
            parameter=sensor_type,
            region_path=region_path,
            window_from=window_from,
            window_to=window_to,
            cache_dir=cache_dir,
            dry_run=args.dry_run,
            no_persist=args.no_persist,
            sensor_id=sensor_id,
            resolution=resolution,
        )
        result["sensor_id"] = sensor_id
        result["sensor_type"] = sensor_type
        result["resolution"] = resolution
        results.append(result)
        print(
            f"  {sensor_id} (code={sinca_code} {region_path} "
            f"{sensor_type}/{resolution}): {result['status']} "
            f"records={result['records']} written={result['written']}"
        )

    ok = sum(
        1 for r in results
        if r["status"].endswith("-parsed") or r["status"].endswith("-persisted")
    )
    failed = len(results) - ok
    total_records = sum(r["records"] for r in results)
    total_written = sum(r["written"] for r in results)
    print(
        f"batch summary: {ok}/{len(results)} OK, {failed} failed; "
        f"records={total_records} written={total_written}"
    )
    return 0 if failed == 0 else 1


# ---------------------------------------------------------------------------
# Weather ingest (L.M.1): Open-Meteo live + ERA5 stub
# ---------------------------------------------------------------------------


def _http_get_json(url: str, *, timeout_seconds: float = 60.0) -> Mapping[str, Any]:
    """Fetch a JSON URL. stdlib only — Open-Meteo's archive API is JSON."""
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "DustOps-AI/0.1 (research; contact: ignacio@dustops.ai)",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as resp:
        body = resp.read().decode("utf-8")
    parsed = json.loads(body)
    if not isinstance(parsed, dict):
        raise ValueError(
            f"expected JSON object at {url}, got {type(parsed).__name__}"
        )
    return parsed


def _persist_weather(
    *,
    source: str,
    parsed: Iterable[Mapping[str, Any]],
    zone_id: str | None,
    weather_target_id: str,
    realtime_proxy: bool,
) -> int:
    """Persist parsed weather records into `weather_readings`.

    M.2: requires `weather_target_id` (target identity from
    data_seed/<mine>.yaml `weather_targets:`) and `realtime_proxy`
    (True for Open-Meteo/DGA/POWER; False for ERA5/MERRA-2). Idempotent:
    re-runs on the same window are a no-op via SQLite `INSERT OR IGNORE`
    against the unique constraint `(source, weather_target_id, timestamp)`.
    Returns the number of rows actually written (excluding skipped
    duplicates).
    """
    Base.metadata.create_all(get_engine())
    written = 0
    skipped = 0
    with session_scope() as session:
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        for rec in parsed:
            stmt = (
                sqlite_insert(WeatherReading)
                .values(
                    source=source,
                    zone_id=zone_id,
                    timestamp=rec["timestamp"],
                    weather_target_id=weather_target_id,
                    realtime_proxy=realtime_proxy,
                    wind_speed_ms=rec.get("wind_speed_ms"),
                    wind_direction_deg=rec.get("wind_direction_deg"),
                    gust_speed_ms=rec.get("gust_speed_ms"),
                    humidity_pct=rec.get("humidity_pct"),
                    temperature_c=rec.get("temperature_c"),
                    pressure_hpa=rec.get("pressure_hpa"),
                    rainfall_mm_15min=rec.get("rainfall_mm_15min"),
                    solar_wm2=rec.get("solar_wm2"),
                    visibility_m=rec.get("visibility_m"),
                    cloud_cover_pct=rec.get("cloud_cover_pct"),
                    mixing_height_m=rec.get("mixing_height_m"),
                )
                .prefix_with("OR IGNORE")
            )
            result = session.execute(stmt)
            rowcount: int = getattr(result, "rowcount", 0) or 0
            if rowcount > 0:
                written += 1
            else:
                skipped += 1
    if skipped:
        print(f"  weather persist: {skipped} duplicate row(s) skipped (idempotent)")
    return written


def _run_one_open_meteo(
    *,
    latitude: float,
    longitude: float,
    window_from: datetime,
    window_to: datetime,
    cache_dir: Path,
    dry_run: bool,
    no_persist: bool,
    zone_id: str | None,
    weather_target_id: str,
) -> dict[str, Any]:
    """Execute one (point, window) Open-Meteo pull. Returns a status dict.

    M.2: `weather_target_id` is required and is written to every
    persisted row. Open-Meteo is tagged `realtime_proxy=True`.
    """
    cache_filters = {"latitude": float(latitude), "longitude": float(longitude)}
    cached = ingest_cache.get(
        source=OPEN_METEO_SOURCE,
        window_from=window_from,
        window_to=window_to,
        filters=cache_filters,
        cache_dir=cache_dir,
    )
    if cached is not None:
        payload: Mapping[str, Any] = cached
        source_tag = "cache"
    elif dry_run:
        return {
            "latitude": latitude,
            "longitude": longitude,
            "status": "dry-run-no-cache",
            "records": 0,
            "written": 0,
        }
    else:
        url = build_open_meteo_url(
            latitude=latitude,
            longitude=longitude,
            window_from=window_from,
            window_to=window_to,
        )
        try:
            payload = _http_get_json(url)
        except (urllib.error.URLError, ValueError) as exc:
            return {
                "latitude": latitude,
                "longitude": longitude,
                "status": "http-error",
                "error": str(exc),
                "records": 0,
                "written": 0,
            }
        ingest_cache.put(
            payload=payload,
            source=OPEN_METEO_SOURCE,
            window_from=window_from,
            window_to=window_to,
            filters=cache_filters,
            cache_dir=cache_dir,
        )
        source_tag = "live"

    parsed = parse_open_meteo_payload(payload, zone_id=zone_id)
    if no_persist:
        return {
            "latitude": latitude,
            "longitude": longitude,
            "status": f"{source_tag}-parsed",
            "records": len(parsed),
            "written": 0,
        }
    written = _persist_weather(
        source=OPEN_METEO_SOURCE,
        parsed=parsed,
        zone_id=zone_id,
        weather_target_id=weather_target_id,
        realtime_proxy=True,
    )
    return {
        "latitude": latitude,
        "longitude": longitude,
        "status": f"{source_tag}-persisted",
        "records": len(parsed),
        "written": written,
        "zone_id": zone_id,
        "weather_target_id": weather_target_id,
    }


def cmd_open_meteo(args: argparse.Namespace) -> int:
    if args.latitude is None or args.longitude is None:
        print(
            "--latitude and --longitude are required for --source open_meteo "
            "(or use --from-yaml)",
            file=sys.stderr,
        )
        return 2
    if not args.no_persist and not args.weather_target_id:
        print(
            "--weather-target-id is required when persisting open_meteo "
            "rows (M.2 anti-hindsight contract). Add a `weather_targets:` "
            "entry to your YAML and pass --weather-target-id <id>, or use "
            "--from-yaml.",
            file=sys.stderr,
        )
        return 2
    print(f"open-meteo: {OPEN_METEO_LICENSE_NOTE}")
    cache_dir = Path(args.cache_dir)
    window_from = _parse_date(args.window_from)
    window_to = _parse_date(args.window_to)
    result = _run_one_open_meteo(
        latitude=args.latitude,
        longitude=args.longitude,
        window_from=window_from,
        window_to=window_to,
        cache_dir=cache_dir,
        dry_run=args.dry_run,
        no_persist=args.no_persist,
        zone_id=args.zone_id,
        weather_target_id=args.weather_target_id or "single-point-cli",
    )
    status = result["status"]
    if status == "dry-run-no-cache":
        print("dry-run: no cache entry and live fetch disabled; exiting 0")
        return 0
    if status == "http-error":
        print(f"http error: {result['error']}", file=sys.stderr)
        return 2
    if status.endswith("-parsed"):
        print(f"parsed {result['records']} records (no-persist mode)")
        return 0
    print(
        f"wrote {result['written']} WeatherReading rows for "
        f"zone_id={result.get('zone_id')!r} (source=open_meteo)"
    )
    return 0


def cmd_open_meteo_from_yaml(args: argparse.Namespace) -> int:
    """Drive an Open-Meteo batch from `weather_targets:` in an RCA-seed YAML."""
    print(f"open-meteo: {OPEN_METEO_LICENSE_NOTE}")
    cache_dir = Path(args.cache_dir)
    window_from = _parse_date(args.window_from)
    window_to = _parse_date(args.window_to)
    yaml_path = Path(args.from_yaml)
    doc = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    targets = doc.get("weather_targets") or []
    print(f"yaml: {len(targets)} weather_target(s)")
    if not targets:
        print(
            "  no weather_targets in YAML; add a `weather_targets:` block",
            file=sys.stderr,
        )
        return 1

    results: list[dict[str, Any]] = []
    for spec in targets:
        target_id = spec["target_id"]
        latitude = float(spec["latitude"])
        longitude = float(spec["longitude"])
        zone_id = spec.get("zone_id")  # optional; usually None for non-zone points
        result = _run_one_open_meteo(
            latitude=latitude,
            longitude=longitude,
            window_from=window_from,
            window_to=window_to,
            cache_dir=cache_dir,
            dry_run=args.dry_run,
            no_persist=args.no_persist,
            zone_id=zone_id,
            weather_target_id=target_id,
        )
        result["target_id"] = target_id
        results.append(result)
        print(
            f"  {target_id} ({latitude},{longitude} zone={zone_id!r}): "
            f"{result['status']} records={result['records']} "
            f"written={result['written']}"
        )

    ok = sum(
        1 for r in results
        if r["status"].endswith("-parsed") or r["status"].endswith("-persisted")
    )
    failed = len(results) - ok
    total_records = sum(r["records"] for r in results)
    total_written = sum(r["written"] for r in results)
    print(
        f"batch summary: {ok}/{len(results)} OK, {failed} failed; "
        f"records={total_records} written={total_written}"
    )
    return 0 if failed == 0 else 1


def cmd_era5_from_payload(args: argparse.Namespace) -> int:
    """ERA5 stub mode (L.M.1): load a pre-extracted JSON payload.

    Full CDS-API integration (auth + async + NetCDF→JSON) is L.M.2.
    For now, the operator runs the CDS extraction out of band, lands
    a JSON file matching `parse_era5_payload`'s expected shape, and
    feeds it through here. This unblocks ERA5-side downstream work
    without dragging the cdsapi dependency into CI.
    """
    if not args.era5_payload:
        print(
            "--era5-payload PATH is required for --source era5 (full CDS-API "
            "live mode is deferred to L.M.2)",
            file=sys.stderr,
        )
        return 2
    if not args.no_persist and not args.weather_target_id:
        print(
            "--weather-target-id is required when persisting ERA5 rows "
            "(M.2 anti-hindsight contract; ERA5 is reanalysis, "
            "realtime_proxy=False).",
            file=sys.stderr,
        )
        return 2
    payload_path = Path(args.era5_payload)
    if not payload_path.exists():
        print(f"era5 payload not found: {payload_path}", file=sys.stderr)
        return 2
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    parsed = parse_era5_payload(payload, zone_id=args.zone_id)
    print(f"era5: parsed {len(parsed)} records from {payload_path}")
    if args.no_persist:
        return 0
    written = _persist_weather(
        source=ERA5_SOURCE,
        parsed=parsed,
        zone_id=args.zone_id,
        weather_target_id=args.weather_target_id or "era5-payload-cli",
        realtime_proxy=False,
    )
    print(
        f"wrote {written} WeatherReading rows for zone_id={args.zone_id!r} "
        f"target_id={args.weather_target_id!r} (source=era5, realtime_proxy=False)"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        default="sinca",
        choices=["sinca", "open_meteo", "era5"],
    )
    parser.add_argument("--station", required=False, help="SINCA station code")
    parser.add_argument("--station-name", default=None)
    parser.add_argument("--region", default=None)
    parser.add_argument("--commune", default=None)
    parser.add_argument("--longitude", type=float, default=None)
    parser.add_argument("--latitude", type=float, default=None)
    parser.add_argument(
        "--tier", default="EMRPM", choices=["EMRPM", "indicative"]
    )
    parser.add_argument(
        "--region-path",
        default="RM",
        help="SINCA macropath region segment (RM, RIV, RV, ...)",
    )
    parser.add_argument(
        "--parameter", default="pm10", choices=["pm10", "pm25"]
    )
    parser.add_argument("--from", dest="window_from", required=False)
    parser.add_argument("--to", dest="window_to", required=False)
    parser.add_argument("--mine-id", default=None)
    parser.add_argument("--sensor-id", default=None)
    parser.add_argument(
        "--cache-dir", default=str(ROOT / "data_cache"), help="Disk cache root"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Use cache only; do not perform live HTTP",
    )
    parser.add_argument(
        "--no-persist",
        action="store_true",
        help="Parse only; do not write to the database",
    )
    parser.add_argument(
        "--from-yaml",
        dest="from_yaml",
        default=None,
        help=(
            "Drive a batch pull from an RCA-seed YAML file. Iterates "
            "every sensor with a non-null sinca_station_code; uses "
            "each sensor's sinca_region_path (falls back to "
            "--region-path)."
        ),
    )
    parser.add_argument(
        "--include-empty",
        action="store_true",
        help=(
            "When using --from-yaml, also pull sensors flagged "
            "sinca_data_status=no_published_data. Default: skip them, "
            "since they return all-empty CSVs."
        ),
    )
    parser.add_argument(
        "--resolution",
        default="horario",
        choices=["horario", "diario"],
        help="SINCA macro resolution for single-station mode; "
        "ignored under --from-yaml (per-sensor sinca_resolution wins).",
    )
    # L.M.1: weather-source flags. --latitude/--longitude are reused
    # from the SINCA single-station block above (they are optional on
    # both paths). --zone-id and --era5-payload are weather-only.
    parser.add_argument(
        "--zone-id",
        default=None,
        help="zone_id to tag on weather_readings rows (None = site-wide).",
    )
    parser.add_argument(
        "--era5-payload",
        default=None,
        help=(
            "Path to a pre-extracted ERA5 JSON file "
            "(see app/ingestion/public/era5.py for the expected shape). "
            "L.M.1 ERA5 stub mode; full CDS-API integration is L.M.2."
        ),
    )
    parser.add_argument(
        "--weather-target-id",
        dest="weather_target_id",
        default=None,
        help=(
            "Weather target identity (matches `target_id` in the YAML "
            "weather_targets list). Required for single-point persists "
            "of --source open_meteo / --source era5 (M.2 anti-hindsight "
            "contract). Auto-supplied per-row under --from-yaml."
        ),
    )

    args = parser.parse_args(argv)

    if args.source == "sinca":
        if not args.window_from or not args.window_to:
            parser.error("--from and --to are required for --source sinca")
        if args.from_yaml:
            return cmd_sinca_from_yaml(args)
        if not args.station:
            parser.error("--station or --from-yaml is required for --source sinca")
        return cmd_sinca(args)
    if args.source == "open_meteo":
        if not args.window_from or not args.window_to:
            parser.error("--from and --to are required for --source open_meteo")
        if args.from_yaml:
            return cmd_open_meteo_from_yaml(args)
        return cmd_open_meteo(args)
    if args.source == "era5":
        return cmd_era5_from_payload(args)
    parser.error(f"unsupported source: {args.source}")
    return 2  # unreachable; satisfies type checker


if __name__ == "__main__":
    sys.exit(main())
