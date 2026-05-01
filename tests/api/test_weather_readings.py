from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.storage.models import IngestError


def test_post_weather_persists(client: TestClient) -> None:
    body = {
        "source": "onsite_station_1",
        "timestamp": datetime.now(UTC).isoformat(),
        "wind_speed_ms": 14.2,
        "wind_direction_deg": 72,
        "humidity_pct": 38,
    }
    r = client.post("/api/v1/weather-readings", json=body)
    assert r.status_code == 201, r.text
    assert r.json()["wind_speed_ms"] == 14.2


def test_post_weather_invalid_humidity_logged(client: TestClient, api_engine: Engine) -> None:
    body = {
        "source": "x",
        "timestamp": datetime.now(UTC).isoformat(),
        "humidity_pct": 250,
    }
    r = client.post("/api/v1/weather-readings", json=body)
    assert r.status_code == 422
    factory = sessionmaker(bind=api_engine, future=True)
    with factory() as s:
        assert s.query(IngestError).count() == 1


def test_get_weather_empty(client: TestClient) -> None:
    r = client.get("/api/v1/weather-readings")
    assert r.status_code == 200
    assert r.json() == []
