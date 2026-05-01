from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.models import registry
from app.storage.models import (
    Mine,
    Sensor,
    SensorReading,
    WeatherReading,
    Zone,
)


def _seed(api_engine: Engine) -> None:
    factory = sessionmaker(bind=api_engine, future=True)
    with factory() as s:
        s.add(Mine(mine_id="m1", name="Demo m1"))
        s.add(
            Zone(
                zone_id="haul_c",
                mine_id="m1",
                zone_type="haul_road",
                operational_importance="high",
                dust_generation_baseline="medium",
            )
        )
        s.add(Sensor(sensor_id="cs1", mine_id="m1", zone_id="haul_c", sensor_type="pm10"))
        now = datetime.now(UTC).replace(tzinfo=None)
        for mins_ago, pm10 in [(2.0, 80.0), (10.0, 60.0), (20.0, 50.0)]:
            s.add(
                SensorReading(
                    sensor_id="cs1",
                    timestamp=now - timedelta(minutes=mins_ago),
                    raw_value={"pm10_ugm3": pm10, "pm25_ugm3": pm10 * 0.4},
                )
            )
        s.add(
            WeatherReading(
                source="onsite",
                zone_id=None,
                timestamp=now - timedelta(minutes=1),
                wind_speed_ms=4.0,
                wind_direction_deg=180.0,
                gust_speed_ms=6.0,
                humidity_pct=45.0,
            )
        )
        s.commit()


def test_current_forecast_returns_safety_fields(client: TestClient, api_engine: Engine) -> None:
    _seed(api_engine)
    r = client.get(
        "/api/v1/forecasts/current",
        params={"target_kind": "zone", "target_id": "haul_c", "horizon": "60min"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body is not None
    assert body["target_id"] == "haul_c"
    assert body["forecast_horizon"] == "60min"
    assert body["model_version"].startswith("dust_forecast_heuristic_")
    assert body["feature_pipeline_version"] == "feature_pipeline_v0.1.0"
    assert 0.0 <= body["confidence"] <= 1.0
    assert 0.0 <= body["breach_probability"] <= 1.0
    assert body["source"] in {"model", "heuristic_fallback"}


def test_current_forecast_empty_db_returns_null(client: TestClient) -> None:
    """Smoke happy-path: no zones registered -> 200 + null body."""
    r = client.get("/api/v1/forecasts/current")
    assert r.status_code == 200
    assert r.json() is None


def test_current_forecast_single_zone_defaults_to_it(
    client: TestClient, api_engine: Engine
) -> None:
    _seed(api_engine)
    r = client.get("/api/v1/forecasts/current")
    assert r.status_code == 200
    body = r.json()
    assert body is not None
    assert body["target_id"] == "haul_c"


def test_current_forecast_unknown_zone_404s(client: TestClient, api_engine: Engine) -> None:
    _seed(api_engine)
    r = client.get(
        "/api/v1/forecasts/current",
        params={"target_kind": "zone", "target_id": "ghost"},
    )
    assert r.status_code == 404


def test_current_forecast_invalid_horizon_rejected(
    client: TestClient, api_engine: Engine
) -> None:
    _seed(api_engine)
    r = client.get(
        "/api/v1/forecasts/current",
        params={"target_kind": "zone", "target_id": "haul_c", "horizon": "90min"},
    )
    assert r.status_code == 422


def test_history_returns_persisted_predictions(client: TestClient, api_engine: Engine) -> None:
    _seed(api_engine)
    # Issue two forecasts so history has rows
    for horizon in ("15min", "60min"):
        r = client.get(
            "/api/v1/forecasts/current",
            params={"target_kind": "zone", "target_id": "haul_c", "horizon": horizon},
        )
        assert r.status_code == 200, r.text

    r = client.get(
        "/api/v1/forecasts/history",
        params={"target_kind": "zone", "target_id": "haul_c"},
    )
    assert r.status_code == 200
    history = r.json()
    assert len(history) == 2
    horizons = {h["forecast_horizon"] for h in history}
    assert horizons == {"15min", "60min"}


def test_history_empty_when_target_unknown(client: TestClient, api_engine: Engine) -> None:
    _seed(api_engine)
    r = client.get(
        "/api/v1/forecasts/history",
        params={"target_kind": "zone", "target_id": "ghost"},
    )
    assert r.status_code == 200
    assert r.json() == []


def test_baseline_self_registers_when_registry_empty(
    client: TestClient, api_engine: Engine
) -> None:
    """Process-global registry quirk: even if a prior test reset it,
    the route's lazy registration should restore the baseline."""
    registry.reset()
    _seed(api_engine)
    r = client.get(
        "/api/v1/forecasts/current",
        params={"target_kind": "zone", "target_id": "haul_c"},
    )
    assert r.status_code == 200
    assert r.json()["model_version"].startswith("dust_forecast_heuristic_")
