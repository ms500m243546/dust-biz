from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.storage.models import IngestError, Sensor, SensorReading


def _seed_sensor(api_engine: Engine) -> None:
    factory = sessionmaker(bind=api_engine, future=True)
    with factory() as s:
        from app.storage.models import Mine

        s.add(Mine(mine_id="m1", name="Test"))
        s.add(Sensor(sensor_id="S1", mine_id="m1", sensor_type="pm10"))
        s.commit()


def test_post_sensor_reading_persists(client: TestClient, api_engine: Engine) -> None:
    _seed_sensor(api_engine)
    body = {
        "sensor_id": "S1",
        "timestamp": datetime.now(UTC).isoformat(),
        "raw_value": {"pm10_ugm3": 118},
    }
    r = client.post("/api/v1/sensor-readings", json=body)
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["sensor_id"] == "S1"
    assert data["raw_value"]["pm10_ugm3"] == 118
    assert data["received_at"] is not None


def test_post_sensor_reading_invalid_lands_in_ingest_errors(
    client: TestClient, api_engine: Engine
) -> None:
    body = {"sensor_id": "S1", "raw_value": "not-a-dict"}  # missing timestamp, wrong type
    r = client.post("/api/v1/sensor-readings", json=body)
    assert r.status_code == 422

    factory = sessionmaker(bind=api_engine, future=True)
    with factory() as s:
        rows = s.query(IngestError).all()
        assert len(rows) == 1
        assert rows[0].source_endpoint == "POST /api/v1/sensor-readings"
        assert rows[0].raw_payload["sensor_id"] == "S1"
        assert len(rows[0].validation_errors) >= 1


def test_post_sensor_reading_batch(client: TestClient, api_engine: Engine) -> None:
    _seed_sensor(api_engine)
    now = datetime.now(UTC)
    body = [
        {
            "sensor_id": "S1",
            "timestamp": (now - timedelta(minutes=i)).isoformat(),
            "raw_value": {"pm10_ugm3": 100 + i},
        }
        for i in range(3)
    ]
    r = client.post("/api/v1/sensor-readings/batch", json=body)
    assert r.status_code == 201, r.text
    assert len(r.json()) == 3


def test_post_sensor_reading_batch_partial_failure(
    client: TestClient, api_engine: Engine
) -> None:
    _seed_sensor(api_engine)
    now = datetime.now(UTC)
    body = [
        {"sensor_id": "S1", "timestamp": now.isoformat(), "raw_value": {"pm10_ugm3": 100}},
        {"sensor_id": "S1", "raw_value": "bad"},  # invalid
    ]
    r = client.post("/api/v1/sensor-readings/batch", json=body)
    assert r.status_code == 422
    assert r.json()["detail"]["rejected_indices"] == [1]

    factory = sessionmaker(bind=api_engine, future=True)
    with factory() as s:
        # Whole batch is rejected (no partial commit) - only the invalid
        # item appears in ingest_errors.
        readings = s.query(SensorReading).all()
        assert len(readings) == 0
        errors = s.query(IngestError).all()
        assert len(errors) == 1


def test_get_sensor_readings_empty(client: TestClient) -> None:
    r = client.get("/api/v1/sensor-readings")
    assert r.status_code == 200
    assert r.json() == []


def test_get_sensor_readings_filter_by_sensor(client: TestClient, api_engine: Engine) -> None:
    _seed_sensor(api_engine)
    now = datetime.now(UTC).isoformat()
    client.post(
        "/api/v1/sensor-readings",
        json={"sensor_id": "S1", "timestamp": now, "raw_value": {"pm10_ugm3": 99}},
    )
    r = client.get("/api/v1/sensor-readings", params={"sensor_id": "S1"})
    assert r.status_code == 200
    assert len(r.json()) == 1
