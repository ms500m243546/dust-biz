from fastapi.testclient import TestClient

import app as app_pkg
from app.api.main import app


def test_meta_returns_identity() -> None:
    client = TestClient(app)
    r = client.get("/api/v1/meta")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "DustOps AI"
    assert body["version"] == app_pkg.__version__
    assert body["api_version"] == "v1"
    assert isinstance(body["current_phase"], str)
    assert isinstance(body["completed_phases"], list)


def test_meta_phase_state_is_consistent() -> None:
    """current_phase must not also appear in completed_phases."""
    client = TestClient(app)
    body = client.get("/api/v1/meta").json()
    assert body["current_phase"] not in body["completed_phases"]
