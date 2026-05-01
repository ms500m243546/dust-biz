"""Orchestrator tests.

Verify the join logic, error paths, and persistence. Feeds the
orchestrator with hand-built forecast + mine-state snapshots so the
test isolates the simulation join from the forecasting pipeline.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.domain.interventions import (
    UnknownInterventionError,
    seed_default_interventions,
)
from app.domain.simulation import (
    NoForecastError,
    ZoneNotFoundError,
    simulate_do_nothing,
    simulate_intervention,
)
from app.models import registry
from app.storage.models import (
    DustPrediction,
    Mine,
    MineStateSnapshot,
    Zone,
)

T0 = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)


def _seed_world(session: Session) -> None:
    registry.reset()
    session.add(Mine(mine_id="m1", name="Demo"))
    session.add(
        Zone(
            zone_id="haul_c",
            mine_id="m1",
            zone_type="haul_road",
            operational_importance="high",
            dust_generation_baseline="high",
        )
    )
    session.flush()
    session.add(
        MineStateSnapshot(
            timestamp=T0.replace(tzinfo=None),
            zone_id="haul_c",
            activity="hauling",
            equipment_active=["truck_1"],
            production_rate_tph=1000.0,
            dust_generation_potential="high",
            wind_exposure="high",
            downwind_assets=[],
            operational_importance="high",
            staleness_flags=[],
        )
    )
    session.add(
        DustPrediction(
            prediction_id="PRED-20260501-0001",
            issued_at=T0.replace(tzinfo=None),
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
    seed_default_interventions(session)
    session.flush()


def test_simulate_intervention_persists_and_returns_join(session: Session) -> None:
    _seed_world(session)
    out = simulate_intervention(
        session=session,
        intervention_id="water_road",
        target_zone_id="haul_c",
        now=T0,
    )
    assert out.intervention_id == "water_road"
    assert out.target_zone_id == "haul_c"
    # Water road -> 35% reduction => 0.8 * 0.65 = 0.52
    assert abs(out.breach_probability_after - 0.52) < 0.01
    assert out.predicted_pm10_reduction > 0
    assert out.production_loss_tonnes > 0
    assert out.model_version.startswith("intervention_impact_heuristic_")
    assert out.cost_model_version.startswith("production_cost_heuristic_")


def test_simulate_unknown_intervention_raises(session: Session) -> None:
    _seed_world(session)
    with pytest.raises(UnknownInterventionError):
        simulate_intervention(
            session=session,
            intervention_id="dance_for_rain",
            target_zone_id="haul_c",
            now=T0,
        )


def test_simulate_unknown_zone_raises(session: Session) -> None:
    _seed_world(session)
    with pytest.raises(ZoneNotFoundError):
        simulate_intervention(
            session=session,
            intervention_id="water_road",
            target_zone_id="ghost_zone",
            now=T0,
        )


def test_simulate_without_forecast_raises(session: Session) -> None:
    registry.reset()
    session.add(Mine(mine_id="m1", name="Demo"))
    session.add(
        Zone(
            zone_id="haul_c",
            mine_id="m1",
            zone_type="haul_road",
            operational_importance="high",
            dust_generation_baseline="high",
        )
    )
    session.flush()
    seed_default_interventions(session)

    with pytest.raises(NoForecastError):
        simulate_intervention(
            session=session,
            intervention_id="water_road",
            target_zone_id="haul_c",
            now=T0,
        )


def test_do_nothing_returns_unchanged_breach(session: Session) -> None:
    _seed_world(session)
    out = simulate_do_nothing(session=session, target_zone_id="haul_c", now=T0)
    assert out.breach_probability_after == out.breach_probability_before
    assert out.predicted_pm10_reduction == 0.0
    assert out.production_loss_tonnes == 0.0


def test_simulation_persisted_with_sequential_ids(session: Session) -> None:
    _seed_world(session)
    a = simulate_intervention(
        session=session,
        intervention_id="water_road",
        target_zone_id="haul_c",
        now=T0,
    )
    b = simulate_intervention(
        session=session,
        intervention_id="reduce_speed",
        target_zone_id="haul_c",
        now=T0 + timedelta(seconds=1),
    )
    assert a.simulation_id != b.simulation_id
    assert a.simulation_id.startswith("SIM-")
    assert b.simulation_id.startswith("SIM-")


def test_joined_confidence_is_min_of_inputs(session: Session) -> None:
    _seed_world(session)
    out = simulate_intervention(
        session=session,
        intervention_id="reroute_trucks",  # high risk -> lower impact conf
        target_zone_id="haul_c",
        now=T0,
    )
    # impact base 0.55 - 0.10 high penalty = 0.45; cost base 0.65; min = 0.45
    assert abs(out.confidence - 0.45) < 0.01
