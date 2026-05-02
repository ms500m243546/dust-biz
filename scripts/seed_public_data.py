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
    cache_filters = {"station_code": args.station, "parameter": args.parameter}

    cached = ingest_cache.get(
        source=SINCA_SOURCE,
        window_from=window_from,
        window_to=window_to,
        filters=cache_filters,
        cache_dir=cache_dir,
    )

    if cached is not None:
        body = str(cached.get("csv", ""))
        print(f"cache hit: {len(body)} chars from {cache_dir}")
    elif args.dry_run:
        print("dry-run: no cache entry and live fetch disabled; exiting 0")
        return 0
    else:
        url = build_url(
            station_code=args.station,
            parameter=args.parameter,
            window_from=window_from,
            window_to=window_to,
        )
        print(f"fetching: {url}")
        try:
            body = _http_get(url)
        except urllib.error.URLError as exc:
            print(f"http error: {exc}", file=sys.stderr)
            return 2
        ingest_cache.put(
            payload={"csv": body, "url": url},
            source=SINCA_SOURCE,
            window_from=window_from,
            window_to=window_to,
            filters=cache_filters,
            cache_dir=cache_dir,
        )
        print(f"cached {len(body)} chars to {cache_dir}")

    if args.no_persist:
        # Parse only, count rows, don't write to DB. Useful for the
        # very-first live pull when the user wants to verify the URL
        # pattern without polluting the dev DB.
        conn = SincaConnector(cache_dir=cache_dir)
        rows = list(
            conn.fetch_from_payload(
                station=station, parameter=args.parameter, payload=body
            )
        )
        print(f"parsed {len(rows)} records (no-persist mode)")
        return 0

    if not args.sensor_id:
        print("--sensor-id required when persisting", file=sys.stderr)
        return 2
    written = _persist_sinca(
        station=station,
        parameter=args.parameter,
        csv_body=body,
        sensor_id=args.sensor_id,
    )
    print(f"wrote {written} SensorReading rows for sensor_id={args.sensor_id}")
    return 0


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

    args = parser.parse_args(argv)

    if args.source == "sinca":
        if not args.station:
            parser.error("--station is required for --source sinca")
        if not args.window_from or not args.window_to:
            parser.error("--from and --to are required for --source sinca")
        return cmd_sinca(args)
    parser.error(f"unsupported source: {args.source}")
    return 2  # unreachable; satisfies type checker


if __name__ == "__main__":
    sys.exit(main())
