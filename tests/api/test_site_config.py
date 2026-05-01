from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.storage.models import Mine


def _seed_mine(api_engine: Engine, mine_id: str = "m1") -> None:
    factory = sessionmaker(bind=api_engine, future=True)
    with factory() as s:
        s.add(Mine(mine_id=mine_id, name=f"Demo {mine_id}"))
        s.commit()


def test_list_site_configs_empty(client: TestClient) -> None:
    r = client.get("/api/v1/site-config")
    assert r.status_code == 200
    assert r.json() == []


def test_post_site_config_persists(client: TestClient, api_engine: Engine) -> None:
    _seed_mine(api_engine)
    body = {
        "site_id": "m1-main",
        "mine_id": "m1",
        "automation_level": "L1",
        "pm10_thresholds": {"warning": 100.0, "breach": 150.0},
        "pm25_thresholds": {"warning": 25.0, "breach": 35.0},
    }
    r = client.post("/api/v1/site-config", json=body)
    assert r.status_code == 201, r.text
    assert r.json()["site_id"] == "m1-main"

    listed = client.get("/api/v1/site-config").json()
    assert len(listed) == 1
    assert listed[0]["site_id"] == "m1-main"


def test_post_site_config_unknown_mine_returns_400(client: TestClient) -> None:
    body = {
        "site_id": "ghost-main",
        "mine_id": "ghost",
        "automation_level": "L1",
        "pm10_thresholds": {"warning": 100.0, "breach": 150.0},
        "pm25_thresholds": {"warning": 25.0, "breach": 35.0},
    }
    r = client.post("/api/v1/site-config", json=body)
    assert r.status_code == 400


def test_get_site_config_falls_back_for_default_synthetic_id(
    client: TestClient, api_engine: Engine
) -> None:
    _seed_mine(api_engine)
    r = client.get("/api/v1/site-config/default-m1")
    assert r.status_code == 200
    body = r.json()
    assert body["mine_id"] == "m1"
    assert body["automation_level"] == "L1"


def test_get_site_config_unknown_id_returns_404(client: TestClient) -> None:
    r = client.get("/api/v1/site-config/never-existed")
    assert r.status_code == 404


def test_filter_by_mine_id(client: TestClient, api_engine: Engine) -> None:
    _seed_mine(api_engine, "m1")
    _seed_mine(api_engine, "m2")
    for site, mine in [("m1-main", "m1"), ("m2-main", "m2")]:
        client.post(
            "/api/v1/site-config",
            json={
                "site_id": site,
                "mine_id": mine,
                "automation_level": "L1",
                "pm10_thresholds": {"warning": 100.0, "breach": 150.0},
                "pm25_thresholds": {"warning": 25.0, "breach": 35.0},
            },
        )
    only_m1 = client.get("/api/v1/site-config", params={"mine_id": "m1"}).json()
    assert len(only_m1) == 1
    assert only_m1[0]["site_id"] == "m1-main"
