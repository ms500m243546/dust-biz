from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.models import registry
from app.storage.models import (
    DustEvent,
    Equipment,
    EquipmentActivity,
    Mine,
    Sensor,
    SensorReading,
    WeatherReading,
    Zone,
)


def _seed(api_engine: Engine) -> str:
    factory = sessionmaker(bind=api_engine, future=True)
    detected_at = (datetime.now(UTC) - timedelta(minutes=5)).replace(tzinfo=None)
    with factory() as s:
        s.add(Mine(mine_id="m1", name="Demo"))
        s.add(
            Zone(
                zone_id="haul_c",
                mine_id="m1",
                zone_type="haul_road",
                operational_importance="high",
                dust_generation_baseline="high",
            )
        )
        s.add(
            Zone(
                zone_id="idle_pit",
                mine_id="m1",
                zone_type="pit",
                operational_importance="medium",
                dust_generation_baseline="low",
            )
        )
        s.add(Sensor(sensor_id="cs1", mine_id="m1", zone_id="haul_c", sensor_type="pm10"))
        s.add(Equipment(equipment_id="truck_1", mine_id="m1", equipment_type="truck"))
        s.flush()
        for i in range(6):
            s.add(
                EquipmentActivity(
                    equipment_id="truck_1",
                    timestamp=detected_at - timedelta(minutes=2 + i),
                    zone_id="haul_c",
                    activity_type="hauling",
                    tonnage=100.0,
                    raw_payload={},
                )
            )
        for mins_ago, pm10 in [(28, 60.0), (22, 70.0), (12, 110.0), (4, 160.0)]:
            s.add(
                SensorReading(
                    sensor_id="cs1",
                    timestamp=detected_at - timedelta(minutes=mins_ago),
                    raw_value={"pm10_ugm3": pm10, "pm25_ugm3": pm10 * 0.4},
                )
            )
        s.add(
            WeatherReading(
                source="onsite",
                zone_id=None,
                timestamp=detected_at - timedelta(minutes=2),
                wind_speed_ms=4.0,
                wind_direction_deg=180.0,
            )
        )
        s.add(
            DustEvent(
                event_id="EVT-X-001",
                detected_at=detected_at,
                affected_station="cs1",
                peak_pm10=160.0,
                peak_pm25=64.0,
                breach_occurred=True,
                event_source="manual_entry",
                linked_prediction_ids=[],
                notes="visible plume",
            )
        )
        s.commit()
    return "EVT-X-001"


def test_post_attribution_returns_schema_with_safety_fields(
    client: TestClient, api_engine: Engine
) -> None:
    event_id = _seed(api_engine)
    r = client.post(f"/api/v1/attributions/for-event/{event_id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dust_event_id"] == event_id
    assert body["model_version"].startswith("source_attribution_rules_")
    assert 0.0 <= body["confidence"] <= 1.0
    assert any(p["source"] == "haul_c" for p in body["probable_sources"])


def test_post_attribution_unknown_event_404s(client: TestClient) -> None:
    r = client.post("/api/v1/attributions/for-event/EVT-ghost")
    assert r.status_code == 404


def test_get_latest_after_post(client: TestClient, api_engine: Engine) -> None:
    event_id = _seed(api_engine)
    client.post(f"/api/v1/attributions/for-event/{event_id}")
    r = client.get(f"/api/v1/attributions/for-event/{event_id}")
    assert r.status_code == 200
    body = r.json()
    assert body is not None
    assert body["dust_event_id"] == event_id


def test_get_latest_returns_null_when_no_attribution(
    client: TestClient, api_engine: Engine
) -> None:
    _seed(api_engine)
    r = client.get("/api/v1/attributions/for-event/EVT-X-001")
    assert r.status_code == 200
    assert r.json() is None


def test_history_returns_all_attempts(client: TestClient, api_engine: Engine) -> None:
    event_id = _seed(api_engine)
    client.post(f"/api/v1/attributions/for-event/{event_id}")
    client.post(f"/api/v1/attributions/for-event/{event_id}")
    r = client.get(f"/api/v1/attributions/for-event/{event_id}/history")
    assert r.status_code == 200
    history = r.json()
    assert len(history) == 2


def test_list_recent_attributions_empty_db_returns_empty_list(
    client: TestClient,
) -> None:
    """Smoke happy path."""
    r = client.get("/api/v1/attributions")
    assert r.status_code == 200
    assert r.json() == []


def test_list_recent_attributions_returns_after_post(
    client: TestClient, api_engine: Engine
) -> None:
    event_id = _seed(api_engine)
    client.post(f"/api/v1/attributions/for-event/{event_id}")
    r = client.get("/api/v1/attributions")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_baseline_self_registers_when_registry_empty(
    client: TestClient, api_engine: Engine
) -> None:
    registry.reset()
    event_id = _seed(api_engine)
    r = client.post(f"/api/v1/attributions/for-event/{event_id}")
    assert r.status_code == 200
    assert r.json()["model_version"].startswith("source_attribution_rules_")
