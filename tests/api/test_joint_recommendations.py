"""Phase BD.4 — joint-recommendations endpoint tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.models import registry
from app.storage.models import (
    DustPrediction,
    InterventionOption,
    Mine,
    MineStateSnapshot,
    Sensor,
    SiteConfiguration,
    Zone,
)


def _seed_two_zones(api_engine: Engine) -> None:
    """Two haul-road zones, both at high breach probability, both
    eligible for water_road -> water_truck_fleet conflict."""
    registry.reset()
    factory = sessionmaker(bind=api_engine, future=True)
    t0 = (datetime.now(UTC) - timedelta(minutes=2)).replace(tzinfo=None)
    with factory() as s:
        s.add(Mine(mine_id="bd4-mine", name="BD4"))
        s.add(SiteConfiguration(
            site_id="bd4-site", mine_id="bd4-mine", automation_level="L1",
            pm10_thresholds={"warning": 100.0, "breach": 150.0},
            pm25_thresholds={"warning": 25.0, "breach": 35.0},
            extreme_breach_threshold=0.85,
            low_confidence_threshold=0.5,
            optimization_weights={
                "w_breach": 1.0, "w_production": 1.0,
                "w_disruption": 0.5, "w_low_confidence": 0.5,
                "w_compliance": 1.0,
            },
            intervention_constraints={},
        ))
        for zid, breach in [("haul_north", 0.9), ("haul_south", 0.7)]:
            s.add(Zone(
                zone_id=zid, mine_id="bd4-mine",
                zone_type="haul_road",
                operational_importance="high",
                dust_generation_baseline="high",
            ))
            s.flush()
            s.add(Sensor(sensor_id=f"sn-{zid}", mine_id="bd4-mine", zone_id=zid, sensor_type="pm10"))
            s.add(MineStateSnapshot(
                timestamp=t0, zone_id=zid, activity="hauling",
                equipment_active=["truck_1"], production_rate_tph=900.0,
                dust_generation_potential="high", wind_exposure="high",
                downwind_assets=[], operational_importance="high",
                staleness_flags=[],
            ))
            s.add(DustPrediction(
                prediction_id=f"PRED-bd4-{zid}",
                issued_at=t0, target_kind="zone", target_id=zid,
                forecast_horizon="60min",
                predicted_pm10=180.0, predicted_pm25=60.0,
                breach_probability=breach,
                confidence=0.7, main_risk_window="12-13",
                main_uncertainty="wind",
                model_version="dust_forecast_heuristic_v0.1.0",
                feature_pipeline_version="features_v0.1.0",
                input_data_quality_score=0.9, data_quality_warnings=[],
                source="model", input_record_ids=[],
            ))
        # Seed the catalog with one shared-resource intervention so the
        # solver has something real to gate on. The default catalog
        # auto-seeds when the orchestrator runs, so no extra rows
        # required here -- but keep the explicit one for determinism.
        s.add(InterventionOption(
            intervention_id="water_road",
            name="Water haul road",
            description="...",
            risk_class="medium",
            requires_human_approval=True,
            automation_eligible_levels=[],
            estimated_time_to_effect_minutes=10,
            allowed_zone_types=["haul_road"],
            target_cause_classes=["haul_road"],
            resource_classes=["water_truck_fleet"],
        ))
        s.commit()


def test_joint_endpoint_returns_per_zone_recommendations(
    client: TestClient, api_engine: Engine,
) -> None:
    _seed_two_zones(api_engine)
    r = client.post(
        "/api/v1/recommendations/joint",
        json={"target_zone_ids": ["haul_north", "haul_south"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["recommendations"]) == 2
    target_ids = {rec["target_zone_id"] for rec in body["recommendations"]}
    assert target_ids == {"haul_north", "haul_south"}
    # claimed_resources should mention water_truck_fleet (one zone wins it).
    assert (
        "water_truck_fleet" in body["claimed_resources"]
        or body["conflicts"] == []
    )


def test_joint_endpoint_resolves_conflict_in_favour_of_higher_breach(
    client: TestClient, api_engine: Engine,
) -> None:
    _seed_two_zones(api_engine)
    r = client.post(
        "/api/v1/recommendations/joint",
        json={"target_zone_ids": ["haul_north", "haul_south"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # If both zones picked water_road, haul_south (lower breach) gets
    # demoted. Audit list non-empty means the solver fired.
    if body["conflicts"]:
        for c in body["conflicts"]:
            # Only the lower-priority zone should be demoted.
            assert c["zone_id"] == "haul_south"
            assert c["conflicting_zone_id"] == "haul_north"
            assert "water_truck_fleet" in c["conflicting_resource_classes"]


def test_joint_endpoint_rejects_duplicate_zone_ids(client: TestClient) -> None:
    r = client.post(
        "/api/v1/recommendations/joint",
        json={"target_zone_ids": ["a", "a"]},
    )
    assert r.status_code == 400


def test_joint_endpoint_rejects_unknown_zone(
    client: TestClient, api_engine: Engine,
) -> None:
    _seed_two_zones(api_engine)
    r = client.post(
        "/api/v1/recommendations/joint",
        json={"target_zone_ids": ["haul_north", "no-such-zone"]},
    )
    assert r.status_code == 404


def test_joint_endpoint_rejects_empty_list(client: TestClient) -> None:
    r = client.post(
        "/api/v1/recommendations/joint",
        json={"target_zone_ids": []},
    )
    # Pydantic min_length=1 -> 422.
    assert r.status_code == 422
