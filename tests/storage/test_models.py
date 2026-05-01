from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.storage.models import (
    Equipment,
    EquipmentActivity,
    HaulRoadSegment,
    Mine,
    Sensor,
    SensorReading,
    WeatherReading,
    Zone,
)


def test_create_mine_with_zones_and_sensors(session: Session) -> None:
    mine = Mine(mine_id="m1", name="Test Mine")
    zone = Zone(
        zone_id="Haul_Road_C",
        mine_id="m1",
        zone_type="haul_road",
        operational_importance="high",
        dust_generation_baseline="high",
        allowed_interventions=["water_road", "reduce_speed"],
        requires_approval_for=["reduce_truck_flow"],
    )
    sensor = Sensor(
        sensor_id="PM10_STATION_2",
        mine_id="m1",
        sensor_type="pm10",
        is_compliance_station=True,
    )
    session.add_all([mine, zone, sensor])
    session.flush()

    persisted = session.get(Mine, "m1")
    assert persisted is not None
    assert persisted.name == "Test Mine"
    assert len(persisted.zones) == 1
    assert persisted.zones[0].allowed_interventions == ["water_road", "reduce_speed"]
    assert len(persisted.sensors) == 1


def test_sensor_reading_persists_raw_value(session: Session) -> None:
    session.add(Mine(mine_id="m1", name="Test"))
    session.add(Sensor(sensor_id="S1", mine_id="m1", sensor_type="pm10"))
    session.flush()

    reading = SensorReading(
        sensor_id="S1",
        timestamp=datetime.now(UTC),
        raw_value={"pm10_ugm3": 118, "humidity_pct": 38},
    )
    session.add(reading)
    session.flush()

    fetched = session.query(SensorReading).first()
    assert fetched is not None
    assert fetched.raw_value["pm10_ugm3"] == 118


def test_weather_reading_optional_fields_nullable(session: Session) -> None:
    w = WeatherReading(source="onsite", timestamp=datetime.now(UTC))
    session.add(w)
    session.flush()
    assert w.wind_speed_ms is None


def test_equipment_activity_persists(session: Session) -> None:
    session.add(Mine(mine_id="m1", name="Test"))
    session.add(Equipment(equipment_id="Truck_17", mine_id="m1", equipment_type="truck"))
    session.flush()

    activity = EquipmentActivity(
        equipment_id="Truck_17",
        timestamp=datetime.now(UTC),
        activity_type="hauling",
        speed_kmh=31.0,
        tonnage=240.0,
        raw_payload={"gps": [42.1, -71.2]},
    )
    session.add(activity)
    session.flush()

    fetched = session.query(EquipmentActivity).first()
    assert fetched is not None
    assert fetched.activity_type == "hauling"
    assert fetched.raw_payload == {"gps": [42.1, -71.2]}


def test_haul_road_segment(session: Session) -> None:
    session.add(Mine(mine_id="m1", name="Test"))
    seg = HaulRoadSegment(
        segment_id="seg1",
        mine_id="m1",
        from_node="Pit_North",
        to_node="Crusher_1",
        length_m=1850.0,
        surface_type="gravel",
    )
    session.add(seg)
    session.flush()
    assert seg.last_watered_at is None
