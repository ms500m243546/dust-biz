from fastapi.testclient import TestClient

from app.domain.interventions import DEFAULT_INTERVENTIONS


def test_list_lazy_seeds_defaults(client: TestClient) -> None:
    r = client.get("/api/v1/interventions")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == len(DEFAULT_INTERVENTIONS)
    ids = {entry["intervention_id"] for entry in body}
    assert "reduce_speed" in ids
    assert "water_road" in ids


def test_list_returns_safety_fields(client: TestClient) -> None:
    body = client.get("/api/v1/interventions").json()
    by_id = {e["intervention_id"]: e for e in body}
    rs = by_id["reduce_speed"]
    assert rs["risk_class"] == "medium"
    assert rs["requires_human_approval"] is True
    assert rs["automation_eligible_levels"] == []  # G13


def test_get_by_id_404s(client: TestClient) -> None:
    r = client.get("/api/v1/interventions/nope")
    assert r.status_code == 404


def test_get_by_id_returns_seeded_row(client: TestClient) -> None:
    client.get("/api/v1/interventions")  # trigger seed
    r = client.get("/api/v1/interventions/water_road")
    assert r.status_code == 200
    assert r.json()["intervention_id"] == "water_road"


def test_post_upsert_inserts_new(client: TestClient) -> None:
    payload = {
        "intervention_id": "spray_loadout",
        "name": "Spray loading area",
        "description": "Mist suppression at the loadout.",
        "risk_class": "low",
        "requires_human_approval": False,
        "automation_eligible_levels": ["L3"],
        "estimated_time_to_effect_minutes": 5,
        "allowed_zone_types": ["loading_area"],
    }
    r = client.post("/api/v1/interventions", json=payload)
    assert r.status_code == 201, r.text
    r2 = client.get("/api/v1/interventions/spray_loadout")
    assert r2.status_code == 200
    assert r2.json()["name"] == "Spray loading area"
