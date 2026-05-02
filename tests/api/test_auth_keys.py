"""GET /api/v1/auth/keys tests (Phase K.3)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_keys_endpoint_returns_metadata_no_secret(unauthed_client: TestClient) -> None:
    r = unauthed_client.get("/api/v1/auth/keys")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "active_kid" in body
    assert isinstance(body["keys"], list)
    assert all("kid" in k and "alg" in k for k in body["keys"])
    # No key material is ever exposed.
    assert "secret" not in str(body).lower()
