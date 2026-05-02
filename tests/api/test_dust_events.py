from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.storage.models import DustPrediction, Mine, Sensor


def _seed(api_engine: Engine) -> None:
    factory = sessionmaker(bind=api_engine, future=True)
    with factory() as s:
        s.add(Mine(mine_id="m1", name="Demo"))
        s.add(Sensor(sensor_id="cs1", mine_id="m1", sensor_type="pm10"))
        s.commit()


def test_post_manual_event_creates_row(client: TestClient, api_engine: Engine) -> None:
    _seed(api_engine)
    body = {
        "detected_at": "2026-05-01T12:00:00+00:00",
        "affected_station": "cs1",
        "peak_pm10": 180.0,
        "peak_pm25": 70.0,
        "breach_occurred": True,
        "event_source": "manual_entry",
        "notes": "visible plume",
    }
    r = client.post("/api/v1/dust-events", json=body)
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["event_id"].startswith("EVT-")
    assert out["affected_station"] == "cs1"


def test_post_event_unknown_station_404s(client: TestClient, api_engine: Engine) -> None:
    _seed(api_engine)
    r = client.post(
        "/api/v1/dust-events",
        json={
            "detected_at": "2026-05-01T12:00:00+00:00",
            "affected_station": "ghost",
            "peak_pm10": 100.0,
            "peak_pm25": 40.0,
        },
    )
    assert r.status_code == 404


def test_get_events_filters_by_station(client: TestClient, api_engine: Engine) -> None:
    _seed(api_engine)
    factory = sessionmaker(bind=api_engine, future=True)
    with factory() as s:
        s.add(Sensor(sensor_id="cs2", mine_id="m1", sensor_type="pm10"))
        s.commit()

    detected_at = (
        datetime.now(UTC) - timedelta(minutes=5)
    ).isoformat().replace("+00:00", "+00:00")
    for station in ("cs1", "cs2"):
        r = client.post(
            "/api/v1/dust-events",
            json={
                "detected_at": detected_at,
                "affected_station": station,
                "peak_pm10": 100.0,
                "peak_pm25": 40.0,
            },
        )
        assert r.status_code == 201

    r = client.get("/api/v1/dust-events", params={"station": "cs1"})
    assert r.status_code == 200
    bodies = r.json()
    assert len(bodies) == 1
    assert bodies[0]["affected_station"] == "cs1"


def test_get_event_by_id(client: TestClient, api_engine: Engine) -> None:
    _seed(api_engine)
    r = client.post(
        "/api/v1/dust-events",
        json={
            "detected_at": "2026-05-01T12:00:00+00:00",
            "affected_station": "cs1",
            "peak_pm10": 100.0,
            "peak_pm25": 40.0,
        },
    )
    eid = r.json()["event_id"]
    r2 = client.get(f"/api/v1/dust-events/{eid}")
    assert r2.status_code == 200
    assert r2.json()["event_id"] == eid


def test_trigger_from_forecast_creates_event(client: TestClient, api_engine: Engine) -> None:
    _seed(api_engine)
    factory = sessionmaker(bind=api_engine, future=True)
    now = datetime.now(UTC).replace(tzinfo=None)
    with factory() as s:
        s.add(
            DustPrediction(
                prediction_id="PRED-X-1",
                issued_at=now - timedelta(minutes=5),
                target_kind="sensor",
                target_id="cs1",
                forecast_horizon="60min",
                predicted_pm10=170.0,
                predicted_pm25=65.0,
                breach_probability=0.9,
                confidence=0.8,
                main_risk_window="now",
                main_uncertainty="",
                model_version="dust_forecast_heuristic_v0.1.0",
                feature_pipeline_version="feature_pipeline_v0.1.0",
                input_data_quality_score=0.9,
                data_quality_warnings=[],
                source="model",
                input_record_ids=[],
            )
        )
        s.commit()

    r = client.post("/api/v1/dust-events/from-forecast", params={"sensor_id": "cs1"})
    assert r.status_code == 200, r.text
    events = r.json()
    assert len(events) == 1
    assert events[0]["event_source"] == "threshold_trigger"
    assert "PRED-X-1" in events[0]["linked_prediction_ids"]


def test_trigger_unknown_sensor_404s(client: TestClient, api_engine: Engine) -> None:
    _seed(api_engine)
    r = client.post("/api/v1/dust-events/from-forecast", params={"sensor_id": "ghost"})
    assert r.status_code == 404
