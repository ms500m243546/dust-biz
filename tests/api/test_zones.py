from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.storage.models import Mine


def _seed_mine(api_engine: Engine, mine_id: str = "m1") -> None:
    factory = sessionmaker(bind=api_engine, future=True)
    with factory() as s:
        s.add(Mine(mine_id=mine_id, name=f"Demo {mine_id}"))
        s.commit()


def _zone_body(zone_id: str, mine_id: str = "m1") -> dict[str, object]:
    return {
        "zone_id": zone_id,
        "mine_id": mine_id,
        "zone_type": "haul_road",
        "operational_importance": "high",
        "dust_generation_baseline": "medium",
        "allowed_interventions": [],
        "requires_approval_for": [],
    }


def test_list_zones_empty(client: TestClient) -> None:
    r = client.get("/api/v1/zones")
    assert r.status_code == 200
    assert r.json() == []


def test_post_zone_persists(client: TestClient, api_engine: Engine) -> None:
    _seed_mine(api_engine)
    r = client.post("/api/v1/zones", json=_zone_body("z1"))
    assert r.status_code == 201, r.text
    listed = client.get("/api/v1/zones").json()
    assert len(listed) == 1
    assert listed[0]["zone_id"] == "z1"


def test_post_zone_unknown_mine_returns_400(client: TestClient) -> None:
    r = client.post("/api/v1/zones", json=_zone_body("zghost", mine_id="ghost"))
    assert r.status_code == 400


def test_get_zone_by_id_404(client: TestClient) -> None:
    r = client.get("/api/v1/zones/nope")
    assert r.status_code == 404


def test_filter_by_mine_id(client: TestClient, api_engine: Engine) -> None:
    _seed_mine(api_engine, "m1")
    _seed_mine(api_engine, "m2")
    client.post("/api/v1/zones", json=_zone_body("z1", "m1"))
    client.post("/api/v1/zones", json=_zone_body("z2", "m2"))
    only_m1 = client.get("/api/v1/zones", params={"mine_id": "m1"}).json()
    assert [z["zone_id"] for z in only_m1] == ["z1"]
