from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.models import registry
from app.storage.models import (
    DustPrediction,
    Mine,
    MineStateSnapshot,
    Zone,
)


def _seed(api_engine: Engine, *, with_forecast: bool = True) -> None:
    registry.reset()
    factory = sessionmaker(bind=api_engine, future=True)
    t0 = (datetime.now(UTC) - timedelta(minutes=2)).replace(tzinfo=None)
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
                    breach_probability=0.8,
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


def test_post_intervention_returns_joined_simulation(
    client: TestClient, api_engine: Engine
) -> None:
    _seed(api_engine)
    r = client.post(
        "/api/v1/simulations/intervention",
        json={"intervention_id": "water_road", "target_zone_id": "haul_c"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["intervention_id"] == "water_road"
    assert body["target_zone_id"] == "haul_c"
    assert body["predicted_pm10_reduction"] > 0
    assert body["production_loss_tonnes"] > 0
    assert body["model_version"].startswith("intervention_impact_heuristic_")
    assert body["cost_model_version"].startswith("production_cost_heuristic_")
    assert 0.0 <= body["confidence"] <= 1.0


def test_post_intervention_unknown_intervention_404s(
    client: TestClient, api_engine: Engine
) -> None:
    _seed(api_engine)
    r = client.post(
        "/api/v1/simulations/intervention",
        json={"intervention_id": "summon_rain", "target_zone_id": "haul_c"},
    )
    assert r.status_code == 404


def test_post_intervention_unknown_zone_404s(
    client: TestClient, api_engine: Engine
) -> None:
    _seed(api_engine)
    r = client.post(
        "/api/v1/simulations/intervention",
        json={"intervention_id": "water_road", "target_zone_id": "ghost"},
    )
    assert r.status_code == 404


def test_post_intervention_no_forecast_409s(
    client: TestClient, api_engine: Engine
) -> None:
    _seed(api_engine, with_forecast=False)
    r = client.post(
        "/api/v1/simulations/intervention",
        json={"intervention_id": "water_road", "target_zone_id": "haul_c"},
    )
    assert r.status_code == 409


def test_post_do_nothing_baseline(client: TestClient, api_engine: Engine) -> None:
    _seed(api_engine)
    r = client.post(
        "/api/v1/simulations/do-nothing",
        json={"target_zone_id": "haul_c"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["intervention_id"] == "_do_nothing_"
    assert body["predicted_pm10_reduction"] == 0.0
    assert body["production_loss_tonnes"] == 0.0
    assert body["breach_probability_before"] == body["breach_probability_after"]


def test_list_recent_simulations_empty(client: TestClient) -> None:
    """Smoke happy path."""
    r = client.get("/api/v1/simulations")
    assert r.status_code == 200
    assert r.json() == []


def test_list_recent_simulations_after_post(
    client: TestClient, api_engine: Engine
) -> None:
    _seed(api_engine)
    client.post(
        "/api/v1/simulations/intervention",
        json={"intervention_id": "water_road", "target_zone_id": "haul_c"},
    )
    r = client.get("/api/v1/simulations")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["intervention_id"] == "water_road"


def test_list_filters_by_zone(client: TestClient, api_engine: Engine) -> None:
    _seed(api_engine)
    client.post(
        "/api/v1/simulations/intervention",
        json={"intervention_id": "water_road", "target_zone_id": "haul_c"},
    )
    r = client.get("/api/v1/simulations", params={"target_zone_id": "haul_c"})
    assert r.status_code == 200
    assert len(r.json()) == 1
    r2 = client.get("/api/v1/simulations", params={"target_zone_id": "ghost"})
    assert r2.status_code == 200
    assert r2.json() == []
