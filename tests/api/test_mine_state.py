from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.storage.models import Equipment, EquipmentActivity, Mine, WeatherReading, Zone


def _seed(api_engine: Engine) -> None:
    factory = sessionmaker(bind=api_engine, future=True)
    with factory() as s:
        s.add(Mine(mine_id="m1", name="Demo m1"))
        s.add(
            Zone(
                zone_id="haul_c",
                mine_id="m1",
                zone_type="haul_road",
                operational_importance="high",
                dust_generation_baseline="medium",
            )
        )
        s.add(
            Zone(
                zone_id="boundary_n",
                mine_id="m1",
                zone_type="boundary",
                operational_importance="high",
                dust_generation_baseline="low",
            )
        )
        s.add(Equipment(equipment_id="truck_1", mine_id="m1", equipment_type="truck"))
        now = datetime.now(UTC).replace(tzinfo=None)
        s.add(
            EquipmentActivity(
                equipment_id="truck_1",
                timestamp=now - timedelta(minutes=2),
                zone_id="haul_c",
                activity_type="hauling",
                tonnage=120.0,
                raw_payload={},
            )
        )
        s.add(
            WeatherReading(
                source="onsite",
                zone_id=None,
                timestamp=now - timedelta(minutes=1),
                wind_speed_ms=8.0,
                wind_direction_deg=270.0,
                gust_speed_ms=10.0,
            )
        )
        s.commit()


def test_current_state_returns_zone_payload(client: TestClient, api_engine: Engine) -> None:
    _seed(api_engine)
    r = client.get("/api/v1/mine-state/current", params={"mine_id": "m1"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mine_id"] == "m1"
    assert body["window_minutes"] == 15
    zones = {z["zone_id"]: z for z in body["zones"]}
    assert "haul_c" in zones
    haul = zones["haul_c"]
    assert haul["activity"] == "hauling"
    assert haul["wind_exposure"] == "high"
    assert haul["dust_generation_potential"] in {"medium", "high"}
    assert "boundary_n" in haul["downwind_assets"]


def test_current_state_404_when_mine_missing(client: TestClient) -> None:
    r = client.get("/api/v1/mine-state/current", params={"mine_id": "ghost"})
    assert r.status_code == 404


def test_zone_state_endpoint(client: TestClient, api_engine: Engine) -> None:
    _seed(api_engine)
    r = client.get("/api/v1/mine-state/zones/haul_c")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["zone_id"] == "haul_c"
    assert "staleness_flags" in body


def test_zone_state_404_when_zone_missing(client: TestClient) -> None:
    r = client.get("/api/v1/mine-state/zones/nope")
    assert r.status_code == 404


def test_current_state_empty_db_returns_empty_payload(client: TestClient) -> None:
    # No mines registered -> 200 with empty zones (smoke happy path).
    r = client.get("/api/v1/mine-state/current")
    assert r.status_code == 200
    body = r.json()
    assert body["zones"] == []
    assert body["mine_id"] == ""


def test_current_state_single_mine_defaults_to_it(
    client: TestClient, api_engine: Engine
) -> None:
    _seed(api_engine)
    r = client.get("/api/v1/mine-state/current")
    assert r.status_code == 200
    assert r.json()["mine_id"] == "m1"


def test_current_state_multi_mine_requires_explicit_id(
    client: TestClient, api_engine: Engine
) -> None:
    factory = sessionmaker(bind=api_engine, future=True)
    with factory() as s:
        s.add(Mine(mine_id="m1", name="m1"))
        s.add(Mine(mine_id="m2", name="m2"))
        s.commit()
    r = client.get("/api/v1/mine-state/current")
    assert r.status_code == 400
