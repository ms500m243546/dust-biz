from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.storage.models import (
    Equipment,
    EquipmentActivity,
    Mine,
    Sensor,
    SensorReading,
    WeatherReading,
    Zone,
)
from app.storage.repositories.equipment_activity import EquipmentActivityRepository
from app.storage.repositories.ingest_errors import IngestErrorRepository
from app.storage.repositories.sensor_readings import SensorReadingRepository
from app.storage.repositories.weather_readings import WeatherReadingRepository


def _seed_mine(session: Session) -> None:
    session.add(Mine(mine_id="m1", name="Test"))
    session.add(
        Zone(
            zone_id="Haul_Road_C",
            mine_id="m1",
            zone_type="haul_road",
            operational_importance="high",
            dust_generation_baseline="high",
        )
    )
    session.add(Sensor(sensor_id="S1", mine_id="m1", sensor_type="pm10"))
    session.add(Equipment(equipment_id="Truck_17", mine_id="m1", equipment_type="truck"))
    session.flush()


def test_sensor_reading_repo_add_and_get_recent(session: Session) -> None:
    _seed_mine(session)
    repo = SensorReadingRepository(session)
    now = datetime.now(UTC)

    repo.add("S1", now - timedelta(minutes=10), {"pm10_ugm3": 90})
    repo.add("S1", now - timedelta(minutes=5), {"pm10_ugm3": 110})
    repo.add("S1", now, {"pm10_ugm3": 130})

    recent = repo.get_recent("S1", since=now - timedelta(minutes=7))
    assert len(recent) == 2
    assert recent[0].raw_value["pm10_ugm3"] == 130


def test_sensor_reading_repo_add_many(session: Session) -> None:
    _seed_mine(session)
    repo = SensorReadingRepository(session)
    now = datetime.now(UTC)
    batch = [
        SensorReading(sensor_id="S1", timestamp=now - timedelta(minutes=i), raw_value={"i": i})
        for i in range(5)
    ]
    inserted = repo.add_many(batch)
    assert len(inserted) == 5
    assert all(r.reading_id is not None for r in inserted)


def test_weather_reading_repo_zone_filter(session: Session) -> None:
    _seed_mine(session)
    repo = WeatherReadingRepository(session)
    now = datetime.now(UTC)
    repo.add(
        WeatherReading(
            source="onsite",
            zone_id="Haul_Road_C",
            timestamp=now,
            wind_speed_ms=14.2,
            weather_target_id="zone-haul-road-c",
        )
    )
    repo.add(
        WeatherReading(
            source="onsite",
            zone_id=None,
            timestamp=now,
            wind_speed_ms=10.0,
            weather_target_id="site-wide",
        )
    )

    zone_only = repo.get_recent_for_zone("Haul_Road_C", since=now - timedelta(minutes=1))
    assert len(zone_only) == 1
    assert zone_only[0].wind_speed_ms == 14.2


def test_equipment_activity_repo(session: Session) -> None:
    _seed_mine(session)
    repo = EquipmentActivityRepository(session)
    now = datetime.now(UTC)
    repo.add(
        EquipmentActivity(
            equipment_id="Truck_17",
            timestamp=now,
            activity_type="hauling",
            zone_id="Haul_Road_C",
            speed_kmh=31.0,
        )
    )
    by_eq = repo.get_recent_for_equipment("Truck_17", since=now - timedelta(minutes=1))
    by_zone = repo.get_recent_for_zone("Haul_Road_C", since=now - timedelta(minutes=1))
    assert len(by_eq) == 1
    assert len(by_zone) == 1


def test_ingest_error_repo_records_payload_and_errors(session: Session) -> None:
    repo = IngestErrorRepository(session)
    err = repo.add(
        source_endpoint="POST /api/v1/sensor-readings",
        raw_payload={"sensor_id": "S99", "raw_value": "not-a-dict"},
        validation_errors=[{"field": "raw_value", "message": "must be a dict"}],
        client_request_id="req-abc",
    )
    assert err.error_id is not None
    assert err.received_at is not None

    recent = repo.recent()
    assert len(recent) == 1
    assert recent[0].client_request_id == "req-abc"

    by_endpoint = repo.for_endpoint("POST /api/v1/sensor-readings")
    assert len(by_endpoint) == 1
