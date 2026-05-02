from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.models import registry
from app.storage.models import (
    DustPrediction,
    Mine,
    MineStateSnapshot,
    Sensor,
    SiteConfiguration,
    Zone,
)


def _seed(api_engine: Engine, *, breach: float = 0.7, with_forecast: bool = True) -> None:
    registry.reset()
    factory = sessionmaker(bind=api_engine, future=True)
    t0 = (datetime.now(UTC) - timedelta(minutes=2)).replace(tzinfo=None)
    with factory() as s:
        s.add(Mine(mine_id="m1", name="Demo"))
        s.add(
            SiteConfiguration(
                site_id="m1-default",
                mine_id="m1",
                automation_level="L1",
                pm10_thresholds={"warning": 100.0, "breach": 150.0},
                pm25_thresholds={"warning": 25.0, "breach": 35.0},
                extreme_breach_threshold=0.85,
                low_confidence_threshold=0.5,
                optimization_weights={
                    "w_breach": 1.0,
                    "w_production": 1.0,
                    "w_disruption": 0.5,
                    "w_low_confidence": 0.5,
                    "w_compliance": 1.0,
                },
                intervention_constraints={},
            )
        )
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
            Sensor(sensor_id="cs1", mine_id="m1", zone_id="haul_c", sensor_type="pm10")
        )
        s.flush()
        s.add(
            MineStateSnapshot(
                timestamp=t0,
                zone_id="haul_c",
                activity="hauling",
                equipment_active=["truck_1"],
                production_rate_tph=900.0,
                dust_generation_potential="high",
                wind_exposure="high",
                downwind_assets=[],
                operational_importance="high",
                staleness_flags=[],
            )
        )
        if with_forecast:
            s.add(
                DustPrediction(
                    prediction_id="PRED-20260501-0001",
                    issued_at=t0,
                    target_kind="zone",
                    target_id="haul_c",
                    forecast_horizon="60min",
                    predicted_pm10=180.0,
                    predicted_pm25=60.0,
                    breach_probability=breach,
                    confidence=0.7,
                    main_risk_window="12:00-13:00",
                    main_uncertainty="wind",
                    model_version="dust_forecast_heuristic_v0.1.0",
                    feature_pipeline_version="features_v0.1.0",
                    input_data_quality_score=0.9,
                    data_quality_warnings=[],
                    source="model",
                    input_record_ids=[],
                )
            )
        s.commit()


def test_get_current_empty_world_returns_null(client: TestClient) -> None:
    """Smoke happy path."""
    r = client.get("/api/v1/recommendations/current")
    assert r.status_code == 200
    assert r.json() is None


def test_get_current_one_zone_default(client: TestClient, api_engine: Engine) -> None:
    _seed(api_engine)
    r = client.get("/api/v1/recommendations/current")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body is not None
    assert body["target_zone_id"] == "haul_c"
    assert body["model_version"].startswith("optimization_weighted_")
    assert "Risk:" in body["reason"]


def test_get_current_multiple_zones_requires_target(
    client: TestClient, api_engine: Engine
) -> None:
    _seed(api_engine)
    factory = sessionmaker(bind=api_engine, future=True)
    with factory() as s:
        s.add(
            Zone(
                zone_id="haul_d",
                mine_id="m1",
                zone_type="haul_road",
                operational_importance="medium",
                dust_generation_baseline="medium",
            )
        )
        s.commit()
    r = client.get("/api/v1/recommendations/current")
    assert r.status_code == 400


def test_get_current_no_forecast_409s(client: TestClient, api_engine: Engine) -> None:
    _seed(api_engine, with_forecast=False)
    r = client.get("/api/v1/recommendations/current")
    assert r.status_code == 409


def test_post_issue_persists(client: TestClient, api_engine: Engine) -> None:
    _seed(api_engine)
    r = client.post(
        "/api/v1/recommendations", json={"target_zone_id": "haul_c"}
    )
    assert r.status_code == 200, r.text
    rec_id = r.json()["recommendation_id"]
    r2 = client.get(f"/api/v1/recommendations/{rec_id}")
    assert r2.status_code == 200
    assert r2.json()["recommendation_id"] == rec_id


def test_post_unknown_zone_404s(client: TestClient, api_engine: Engine) -> None:
    _seed(api_engine)
    r = client.post(
        "/api/v1/recommendations", json={"target_zone_id": "ghost"}
    )
    assert r.status_code == 404


def test_list_history_empty(client: TestClient) -> None:
    r = client.get("/api/v1/recommendations")
    assert r.status_code == 200
    assert r.json() == []


def test_list_history_after_issue(client: TestClient, api_engine: Engine) -> None:
    _seed(api_engine)
    client.post("/api/v1/recommendations", json={"target_zone_id": "haul_c"})
    r = client.get("/api/v1/recommendations")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_compliance_priority_surfaces_under_extreme_breach(
    client: TestClient, api_engine: Engine
) -> None:
    _seed(api_engine, breach=0.92)
    r = client.post(
        "/api/v1/recommendations", json={"target_zone_id": "haul_c"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["compliance_priority_triggered"] is True
    assert "compliance" in body["reason"].lower()


def test_get_recommendation_not_found_404s(client: TestClient) -> None:
    r = client.get("/api/v1/recommendations/REC-ghost")
    assert r.status_code == 404
