"""Public-data ingest orchestrator (Phase L.7b).

Wires the public-source connectors (currently: SINCA) to live HTTP
using stdlib `urllib.request` (no new dependency), the disk cache in
`app/ingestion/public/cache.py`, and the existing
`SensorReadingRepository` for persistence.

Usage:

    # Wire-only sanity check, no network. Reads from data_cache/ if a
    # prior run populated it; exits 0 with a count of records written.
    python scripts/seed_public_data.py --source sinca --dry-run

    # Live pull. The user runs this themselves; it hits SINCA's CSV
    # gateway, writes the body to data_cache/sinca/, parses, and
    # persists into the dev SQLite DB (or whatever DUSTOPS_DATABASE_URL
    # points at).
    python scripts/seed_public_data.py --source sinca \\
        --station EM05 --parameter pm10 \\
        --from 2026-04-25 --to 2026-05-01 \\
        --mine-id los-pelambres --sensor-id EM05-CUNCUMEN-PM10

The orchestrator is intentionally explicit about which station, which
parameter, which window, and which sensor row in the DB receives the
ingest. No magic discovery — calibration drift is too costly.

Tests cover the parsing path (fixture replay) — the live HTTP path
is exercised by the operator when running this script.
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.ingestion.public import cache as ingest_cache  # noqa: E402
from app.ingestion.public.sinca import (  # noqa: E402
    SOURCE_NAME as SINCA_SOURCE,
    SincaConnector,
    SincaStation,
    build_url,
    parse_sinca_csv,
    quality_hint_for_tier,
    to_raw_sensor_payload,
)
from app.storage.database import session_scope  # noqa: E402
from app.storage.models import Base, SensorReading  # noqa: E402
from app.storage.database import get_engine  # noqa: E402


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
        body = resp.read()
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
    """Parse a SINCA CSV body and persist as SensorReading rows. Returns count."""
    rows = parse_sinca_csv(
        csv_body, station_code=station.station_code, parameter=parameter
    )
    written = 0
    quality_hint = quality_hint_for_tier(station.tier)
    Base.metadata.create_all(get_engine())
    with session_scope() as session:
        for rec in rows:
            raw_value = to_raw_sensor_payload(rec, station=station)
            session.add(
                SensorReading(
                    sensor_id=sensor_id,
                    timestamp=rec["timestamp"],  # type: ignore[index]
                    raw_value=raw_value,
                    source_quality_hint=quality_hint,
                )
            )
            written += 1
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
        if status == "no_published_data" and not args.include_empty:
            return False
        return True

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="sinca", choices=["sinca"])
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

    args = parser.parse_args(argv)

    if args.source == "sinca":
        if not args.window_from or not args.window_to:
            parser.error("--from and --to are required for --source sinca")
        if args.from_yaml:
            return cmd_sinca_from_yaml(args)
        if not args.station:
            parser.error("--station or --from-yaml is required for --source sinca")
        return cmd_sinca(args)
    parser.error(f"unsupported source: {args.source}")
    return 2  # unreachable; satisfies type checker


if __name__ == "__main__":
    sys.exit(main())
