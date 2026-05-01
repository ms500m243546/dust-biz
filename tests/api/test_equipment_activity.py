from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.storage.models import Equipment, IngestError, Mine


def _seed_equipment(api_engine: Engine) -> None:
    factory = sessionmaker(bind=api_engine, future=True)
    with factory() as s:
        s.add(Mine(mine_id="m1", name="Test"))
        s.add(Equipment(equipment_id="Truck_17", mine_id="m1", equipment_type="truck"))
        s.commit()


def test_post_equipment_activity_persists(client: TestClient, api_engine: Engine) -> None:
    _seed_equipment(api_engine)
    body = {
        "equipment_id": "Truck_17",
        "timestamp": datetime.now(UTC).isoformat(),
        "activity_type": "hauling",
        "zone_id": "Haul_Road_C",
        "speed_kmh": 31.0,
    }
    r = client.post("/api/v1/equipment-activity", json=body)
    assert r.status_code == 201, r.text
    assert r.json()["activity_type"] == "hauling"


def test_post_equipment_activity_invalid_type_logged(
    client: TestClient, api_engine: Engine
) -> None:
    body = {
        "equipment_id": "x",
        "timestamp": datetime.now(UTC).isoformat(),
        "activity_type": "skydiving",
    }
    r = client.post("/api/v1/equipment-activity", json=body)
    assert r.status_code == 422
    factory = sessionmaker(bind=api_engine, future=True)
    with factory() as s:
        assert s.query(IngestError).count() == 1


def test_get_equipment_activity_empty(client: TestClient) -> None:
    r = client.get("/api/v1/equipment-activity")
    assert r.status_code == 200
    assert r.json() == []
