"""In-process smoke test for the running app.

Boots the FastAPI app via TestClient (no network port, no uvicorn
process), hits the required endpoints from
docs/definition-of-done.md ("smoke"), and exits 0 on success.

Endpoints currently asserted (others marked pending until their
sub-step lands):
    /api/v1/health
    /api/v1/meta
"""

from __future__ import annotations

import sys

from fastapi.testclient import TestClient

from app.api.main import app

REQUIRED_ENDPOINTS = [
    ("/api/v1/health", 200),
    ("/api/v1/meta", 200),
    ("/api/v1/sensor-readings", 200),
    ("/api/v1/weather-readings", 200),
    ("/api/v1/equipment-activity", 200),
    ("/api/v1/data-quality", 200),
    ("/api/v1/site-config", 200),
    ("/api/v1/zones", 200),
    ("/api/v1/haul-road-segments", 200),
    ("/api/v1/mine-state/current", 200),
    ("/api/v1/forecasts/current", 200),
    ("/api/v1/dust-events", 200),
    ("/api/v1/attributions", 200),
    ("/api/v1/interventions", 200),
    ("/api/v1/simulations", 200),
    ("/api/v1/recommendations", 200),
    ("/api/v1/recommendations/current", 200),
]

# Phase I auth-gated endpoints - smoke asserts they reject anonymous
# callers, which is the actual contract change. Listed separately so
# the success count above stays meaningful and so the gating is
# explicit.
AUTH_GATED_ENDPOINTS = [
    ("/api/v1/auth/me", 401),
    ("/api/v1/action-outcomes", 401),
]

PENDING_ENDPOINTS: list[tuple[str, str]] = []


def main() -> int:
    client = TestClient(app)
    failures: list[str] = []
    for path, expected_status in REQUIRED_ENDPOINTS:
        r = client.get(path)
        if r.status_code != expected_status:
            failures.append(f"{path}: got {r.status_code}, expected {expected_status}")
    for path, expected_status in AUTH_GATED_ENDPOINTS:
        r = client.get(path)
        if r.status_code != expected_status:
            failures.append(
                f"{path} (auth-gated): got {r.status_code}, expected {expected_status}"
            )

    # Auth-gated POST: login endpoint takes a body and 401s for unknown user.
    r = client.post(
        "/api/v1/auth/login",
        json={"username": "smoke-nobody", "password": "x"},
    )
    if r.status_code != 401:
        failures.append(
            f"/api/v1/auth/login (auth-gated): got {r.status_code}, expected 401"
        )

    if failures:
        for f in failures:
            print(f, file=sys.stderr)
        return 1

    print(
        f"smoke: {len(REQUIRED_ENDPOINTS)} happy-path endpoints OK + "
        f"{len(AUTH_GATED_ENDPOINTS) + 1} auth-gated endpoints reject anonymous"
    )
    if PENDING_ENDPOINTS:
        print(f"       pending: {', '.join(p for p, _ in PENDING_ENDPOINTS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
