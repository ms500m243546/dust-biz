from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.storage.models import Mine, Sensor


def _seed_sensors(api_engine: Engine, sensor_ids: list[str]) -> None:
    factory = sessionmaker(bind=api_engine, future=True)
    with factory() as s:
        s.add(Mine(mine_id="m1", name="Test"))
        for sid in sensor_ids:
            s.add(Sensor(sensor_id=sid, mine_id="m1", sensor_type="pm10"))
        s.commit()


def test_data_quality_empty_when_no_sensors(client: TestClient) -> None:
    r = client.get("/api/v1/data-quality")
    assert r.status_code == 200
    assert r.json() == []


def test_data_quality_lists_all_sensors(client: TestClient, api_engine: Engine) -> None:
    _seed_sensors(api_engine, ["S1", "S2"])
    r = client.get("/api/v1/data-quality")
    assert r.status_code == 200
    body = r.json()
    sensor_ids = {s["sensor_id"] for s in body}
    assert sensor_ids == {"S1", "S2"}
    # No readings -> all offline
    assert all(s["status"] == "offline" for s in body)


def test_data_quality_for_specific_sensor(client: TestClient, api_engine: Engine) -> None:
    _seed_sensors(api_engine, ["S1"])
    # post recent readings via the ingestion endpoint
    now = datetime.now(UTC)
    for i in range(8):
        client.post(
            "/api/v1/sensor-readings",
            json={
                "sensor_id": "S1",
                "timestamp": (now - timedelta(minutes=i)).isoformat(),
                "raw_value": {"pm10_ugm3": 80 + (i % 3)},
            },
        )
    r = client.get("/api/v1/data-quality/S1")
    assert r.status_code == 200
    body = r.json()
    # status may be healthy or degraded depending on slight clock skew;
    # the contract is just that it's no longer "offline".
    assert body["status"] in {"healthy", "degraded"}
    assert body["quality_score"] > 0


def test_data_quality_for_unknown_sensor_returns_404(client: TestClient) -> None:
    r = client.get("/api/v1/data-quality/NEVER_EXISTED")
    assert r.status_code == 404
