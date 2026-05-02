"""RCA seed loader (Phase L.7d).

Reads `data_seed/<mine>.yaml` and writes Mine, SiteConfiguration,
PopulatedPlace, Sensor, and StationThresholdOverride rows to the
configured database. Idempotent: every entity is upserted by primary
key.

Usage:

    # Load the Los Pelambres seed.
    python scripts/seed_rca.py --file data_seed/los_pelambres.yaml

    # Load both pilot mines.
    python scripts/seed_rca.py --file data_seed/los_pelambres.yaml \\
                              --file data_seed/los_bronces.yaml

The validate-rca-seed gate (`scripts/checks/validate-rca-seed.js`)
fails the agent-check if `deployment_tier: production` is set on a
file that still contains `TODO_FROM_RCA` markers. Dev + staging
tolerate placeholders.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.ingestion.public.ine_populated_places import (  # noqa: E402
    _bearing_deg,
    _haversine_m,
)
from app.storage.database import get_engine, session_scope  # noqa: E402
from app.storage.models import (  # noqa: E402
    Base,
    Mine,
    PopulatedPlace,
    Sensor,
    StationThresholdOverride,
)
from app.storage.repositories.receptor import (  # noqa: E402
    PopulatedPlaceRepository,
)
from app.storage.repositories.site_config import (  # noqa: E402
    SiteConfigRepository,
)
from app.storage.repositories.station_thresholds import (  # noqa: E402
    StationThresholdOverrideRepository,
)


def _has_todo(node: object) -> bool:
    """Recursively check whether any string in node is TODO_FROM_RCA."""
    if isinstance(node, str):
        return "TODO_FROM_RCA" in node
    if isinstance(node, dict):
        return any(_has_todo(v) for v in node.values())
    if isinstance(node, list):
        return any(_has_todo(v) for v in node)
    return False


def _is_todo(value: Any) -> bool:
    return isinstance(value, str) and "TODO_FROM_RCA" in value


def load_seed(path: Path) -> int:
    """Load one YAML seed into the DB. Returns count of rows written."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"seed file is not a dict: {path}")

    deployment_tier = raw.get("deployment_tier", "dev")
    if deployment_tier == "production" and _has_todo(raw):
        raise ValueError(
            f"{path.name}: deployment_tier=production but TODO_FROM_RCA "
            "markers remain; populate them before loading"
        )

    mine_block = raw.get("mine") or {}
    centroid_block = raw.get("mine_centroid") or {}
    site_block = raw.get("site_config") or {}
    places = raw.get("populated_places") or []
    sensors = raw.get("sensors") or []
    overrides = raw.get("station_threshold_overrides") or []

    mine_id = mine_block.get("mine_id")
    if not mine_id:
        raise ValueError(f"{path.name}: mine.mine_id is required")

    mine_lon = centroid_block.get("longitude")
    mine_lat = centroid_block.get("latitude")
    if not isinstance(mine_lon, int | float) or not isinstance(mine_lat, int | float):
        raise ValueError(
            f"{path.name}: mine_centroid.longitude/latitude required as numeric"
        )

    written = 0
    Base.metadata.create_all(get_engine())
    with session_scope() as session:
        # Mine
        mine = session.get(Mine, mine_id)
        if mine is None:
            mine = Mine(
                mine_id=mine_id,
                name=mine_block.get("name", mine_id),
                default_automation_level=mine_block.get(
                    "default_automation_level", "L1"
                ),
            )
            session.add(mine)
            written += 1
        else:
            mine.name = mine_block.get("name", mine.name)
            mine.default_automation_level = mine_block.get(
                "default_automation_level", mine.default_automation_level
            )

        # SiteConfiguration
        if site_block.get("site_id"):
            cfg_repo = SiteConfigRepository(session)
            cfg_repo.upsert(
                site_id=site_block["site_id"],
                mine_id=site_block.get("mine_id", mine_id),
                automation_level=site_block.get("automation_level", "L1"),
                pm10_thresholds=site_block.get("pm10_thresholds", {}),
                pm25_thresholds=site_block.get("pm25_thresholds", {}),
                extreme_breach_threshold=float(
                    site_block.get("extreme_breach_threshold", 0.85)
                ),
                low_confidence_threshold=float(
                    site_block.get("low_confidence_threshold", 0.5)
                ),
                approval_expiry_minutes=int(
                    site_block.get("approval_expiry_minutes", 15)
                ),
                optimization_weights=site_block.get("optimization_weights", {}),
                intervention_constraints={},
                cost_curves=site_block.get("cost_curves", {}),
                updated_by="seed_rca",
            )
            written += 1

        # Sensors
        for s in sensors:
            sid = s.get("sensor_id")
            if not sid:
                continue
            existing = session.get(Sensor, sid)
            if existing is None:
                session.add(
                    Sensor(
                        sensor_id=sid,
                        mine_id=s.get("mine_id", mine_id),
                        sensor_type=s.get("sensor_type", "pm10"),
                        is_compliance_station=bool(
                            s.get("is_compliance_station", False)
                        ),
                    )
                )
                written += 1

        # PopulatedPlaces — compute distance + bearing here.
        place_repo = PopulatedPlaceRepository(session)
        for p in places:
            place_id = p.get("place_id")
            lon = p.get("longitude")
            lat = p.get("latitude")
            if not place_id:
                continue
            if _is_todo(lon) or _is_todo(lat):
                # Skip places without coordinates — dev seed.
                continue
            if not isinstance(lon, int | float) or not isinstance(lat, int | float):
                continue
            distance = _haversine_m(mine_lon, mine_lat, float(lon), float(lat))
            bearing = _bearing_deg(mine_lon, mine_lat, float(lon), float(lat))
            pop_raw = p.get("population")
            population: int | None = None
            if isinstance(pop_raw, int) and not isinstance(pop_raw, bool):
                population = pop_raw
            place_repo.upsert(
                PopulatedPlace(
                    place_id=place_id,
                    mine_id=p.get("mine_id", mine_id),
                    name=p.get("name", place_id),
                    kind=p.get("kind", "town"),
                    longitude=float(lon),
                    latitude=float(lat),
                    population=population,
                    distance_to_mine_m=distance,
                    bearing_from_mine_deg=bearing,
                    source=p.get("source", "rca_receptor_list"),
                    source_url=(
                        None if _is_todo(p.get("source_url")) else p.get("source_url")
                    ),
                    notes=p.get("notes"),
                )
            )
            written += 1

        # StationThresholdOverrides
        ovr_repo = StationThresholdOverrideRepository(session)
        for o in overrides:
            sid = o.get("sensor_id")
            if not sid:
                continue
            ovr_repo.upsert_for_sensor(
                StationThresholdOverride(
                    sensor_id=sid,
                    site_id=site_block.get("site_id"),
                    pm10_warning_ugm3=o.get("pm10_warning_ugm3"),
                    pm10_breach_ugm3=o.get("pm10_breach_ugm3"),
                    pm25_warning_ugm3=o.get("pm25_warning_ugm3"),
                    pm25_breach_ugm3=o.get("pm25_breach_ugm3"),
                    rca_reference=o.get("rca_reference"),
                    source_url=(
                        None if _is_todo(o.get("source_url")) else o.get("source_url")
                    ),
                    notes=o.get("notes"),
                )
            )
            written += 1

    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--file",
        action="append",
        required=True,
        help="Path to a YAML seed file; may be passed multiple times.",
    )
    args = parser.parse_args(argv)

    total = 0
    for f in args.file:
        path = Path(f)
        if not path.exists():
            print(f"missing seed file: {path}", file=sys.stderr)
            return 2
        try:
            written = load_seed(path)
        except ValueError as exc:
            print(f"seed load failed for {path}: {exc}", file=sys.stderr)
            return 2
        print(f"{path.name}: wrote {written} rows")
        total += written
    print(f"total rows written: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
