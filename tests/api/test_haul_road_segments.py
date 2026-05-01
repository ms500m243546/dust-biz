from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.storage.models import Mine


def _seed_mine(api_engine: Engine, mine_id: str = "m1") -> None:
    factory = sessionmaker(bind=api_engine, future=True)
    with factory() as s:
        s.add(Mine(mine_id=mine_id, name=f"Demo {mine_id}"))
        s.commit()


def _segment_body(segment_id: str, mine_id: str = "m1") -> dict[str, object]:
    return {
        "segment_id": segment_id,
        "mine_id": mine_id,
        "from_node": "z1",
        "to_node": "z2",
        "length_m": 420.0,
        "surface_type": "gravel",
    }


def test_list_segments_empty(client: TestClient) -> None:
    r = client.get("/api/v1/haul-road-segments")
    assert r.status_code == 200
    assert r.json() == []


def test_post_segment_persists(client: TestClient, api_engine: Engine) -> None:
    _seed_mine(api_engine)
    r = client.post("/api/v1/haul-road-segments", json=_segment_body("seg1"))
    assert r.status_code == 201, r.text
    listed = client.get("/api/v1/haul-road-segments").json()
    assert len(listed) == 1
    assert listed[0]["segment_id"] == "seg1"


def test_post_segment_unknown_mine_returns_400(client: TestClient) -> None:
    r = client.post(
        "/api/v1/haul-road-segments",
        json=_segment_body("seg-ghost", mine_id="ghost"),
    )
    assert r.status_code == 400


def test_get_segment_by_id_404(client: TestClient) -> None:
    r = client.get("/api/v1/haul-road-segments/nope")
    assert r.status_code == 404
