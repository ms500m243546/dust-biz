from fastapi.testclient import TestClient

from app.api.main import app


def test_health_returns_ok() -> None:
    client = TestClient(app)
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_health_is_under_v1_prefix() -> None:
    client = TestClient(app)
    assert client.get("/health").status_code == 404
    assert client.get("/api/v1/health").status_code == 200
