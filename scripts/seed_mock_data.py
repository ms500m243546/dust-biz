"""Seed mock data into the configured DustOps DB.

Phase C.3 - real generator (was a stub through B.5/C.2).

Creates a minimal mine + zone + sensor + equipment if they do not
already exist, then writes synthetic sensor / weather / equipment
streams via the repository layer.

Usage:
    python scripts/seed_mock_data.py --mine demo --hours 6
    python scripts/seed_mock_data.py --mine demo --hours 24 --seed 11
"""

from __future__ import annotations

import argparse
import sys
from datetime import timedelta

from app.ingestion.mock_streams import (
    generate_equipment_activity,
    generate_sensor_readings,
    generate_weather_readings,
    utc_now,
)
from app.storage.database import session_scope
from app.storage.models import Equipment, Mine, Sensor, WeatherReading, Zone
from app.storage.repositories.equipment_activity import EquipmentActivityRepository
from app.storage.repositories.sensor_readings import SensorReadingRepository
from app.storage.repositories.weather_readings import WeatherReadingRepository

DEFAULT_SENSOR_ID = "PM10_BOUNDARY"
DEFAULT_EQUIPMENT_ID = "Truck_17"
DEFAULT_ZONE_ID = "Haul_Road_C"
DEFAULT_WEATHER_SOURCE = "onsite_station_1"


def _ensure_base_entities(session_scope_fn: object, mine_id: str) -> None:
    # session_scope_fn is annotated as object so the import-time signature
    # of session_scope (a context-manager factory) does not leak; the
    # caller hands us the same callable.
    with session_scope() as session:
        if session.get(Mine, mine_id) is None:
            session.add(Mine(mine_id=mine_id, name=f"Demo {mine_id}"))
            session.add(
                Zone(
                    zone_id=DEFAULT_ZONE_ID,
                    mine_id=mine_id,
                    zone_type="haul_road",
                    operational_importance="high",
                    dust_generation_baseline="high",
                    allowed_interventions=["water_road", "reduce_speed"],
                    requires_approval_for=["reduce_truck_flow"],
                )
            )
            session.add(
                Sensor(
                    sensor_id=DEFAULT_SENSOR_ID,
                    mine_id=mine_id,
                    sensor_type="pm10",
                    is_compliance_station=True,
                )
            )
            session.add(
                Equipment(
                    equipment_id=DEFAULT_EQUIPMENT_ID,
                    mine_id=mine_id,
                    equipment_type="truck",
                )
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="DustOps AI mock data seeder")
    parser.add_argument("--mine", default="demo", help="Mine ID to seed (default: demo)")
    parser.add_argument(
        "--hours", type=int, default=1, help="Hours of mock data to generate (default: 1)"
    )
    parser.add_argument("--seed", type=int, default=42, help="RNG seed (default: 42)")
    parser.add_argument(
        "--sensor-interval-s",
        type=int,
        default=60,
        help="Seconds between sensor readings (default: 60)",
    )
    args = parser.parse_args()

    duration = timedelta(hours=args.hours)
    start = utc_now() - duration

    _ensure_base_entities(session_scope, args.mine)

    n_sensor = 0
    n_weather = 0
    n_equipment = 0

    with session_scope() as session:
        sr_repo = SensorReadingRepository(session)
        for r in generate_sensor_readings(
            DEFAULT_SENSOR_ID,
            start,
            duration,
            interval_seconds=args.sensor_interval_s,
            seed=args.seed,
        ):
            sr_repo.add(
                sensor_id=r.sensor_id,
                timestamp=r.timestamp,
                raw_value=r.raw_value,
                source_quality_hint=r.source_quality_hint,
            )
            n_sensor += 1

        wr_repo = WeatherReadingRepository(session)
        for w in generate_weather_readings(
            DEFAULT_WEATHER_SOURCE,
            start,
            duration,
            zone_id=DEFAULT_ZONE_ID,
            seed=args.seed + 1,
        ):
            wr_repo.add(
                WeatherReading(
                    source=w.source,
                    zone_id=w.zone_id,
                    timestamp=w.timestamp,
                    wind_speed_ms=w.wind_speed_ms,
                    wind_direction_deg=w.wind_direction_deg,
                    gust_speed_ms=w.gust_speed_ms,
                    humidity_pct=w.humidity_pct,
                    temperature_c=w.temperature_c,
                )
            )
            n_weather += 1

        ea_repo = EquipmentActivityRepository(session)
        for a in generate_equipment_activity(
            DEFAULT_EQUIPMENT_ID,
            start,
            duration,
            zone_id=DEFAULT_ZONE_ID,
            seed=args.seed + 2,
        ):
            from app.storage.models import EquipmentActivity

            ea_repo.add(
                EquipmentActivity(
                    equipment_id=a.equipment_id,
                    timestamp=a.timestamp,
                    activity_type=a.activity_type,
                    zone_id=a.zone_id,
                    speed_kmh=a.speed_kmh,
                    tonnage=a.tonnage,
                )
            )
            n_equipment += 1

    print(
        f"seeded mine={args.mine} hours={args.hours} seed={args.seed}: "
        f"{n_sensor} sensor, {n_weather} weather, {n_equipment} equipment readings"
    )
    print("set DUSTOPS_MOCK_MODE=true so /api/v1/meta reports mock data is in use.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
