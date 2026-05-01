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
]

PENDING_ENDPOINTS = [
    ("/api/v1/mine-state/current", "Phase D"),
    ("/api/v1/recommendations/current", "Phase H"),
]


def main() -> int:
    client = TestClient(app)
    failures: list[str] = []
    for path, expected_status in REQUIRED_ENDPOINTS:
        r = client.get(path)
        if r.status_code != expected_status:
            failures.append(f"{path}: got {r.status_code}, expected {expected_status}")

    if failures:
        for f in failures:
            print(f, file=sys.stderr)
        return 1

    print(f"smoke: {len(REQUIRED_ENDPOINTS)} endpoints OK in-process via TestClient")
    print(f"       pending: {', '.join(p for p, _ in PENDING_ENDPOINTS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
