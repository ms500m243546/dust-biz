"""Recommendation orchestrator tests.

Verify the join logic across forecast + simulations + optimizer +
attribution, plus G6 high-risk gating, G7 compliance-priority surfacing
in the rendered reason, and G15 audit-link fields.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.domain.interventions import seed_default_interventions
from app.domain.recommendations import (
    NoForecastError,
    ZoneNotFoundError,
    generate_recommendation,
)
from app.domain.simulation import (
    NoForecastError as SimNoForecastError,  # noqa: F401  (sanity-check shared exception)
)
from app.models import registry
from app.storage.models import (
    DustPrediction,
    Mine,
    MineStateSnapshot,
    Sensor,
    SiteConfiguration,
    SourceAttribution,
    Zone,
)

T0 = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)


def _seed(
    session: Session,
    *,
    breach_probability: float = 0.7,
    with_attribution: bool = False,
    with_site_config: bool = True,
) -> None:
    registry.reset()
    session.add(Mine(mine_id="m1", name="Demo"))
    if with_site_config:
        session.add(
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
    session.add(
        Zone(
            zone_id="haul_c",
            mine_id="m1",
            zone_type="haul_road",
            operational_importance="high",
            dust_generation_baseline="high",
        )
    )
    session.add(
        Sensor(sensor_id="cs1", mine_id="m1", zone_id="haul_c", sensor_type="pm10")
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
            breach_probability=breach_probability,
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
    if with_attribution:
        session.add(
            SourceAttribution(
                attribution_id="ATTR-20260501-001",
                dust_event_id="EVT-20260501-001",
                issued_at=T0.replace(tzinfo=None) + timedelta(seconds=1),
                affected_station="haul_c",
                probable_sources=[
                    {"source": "haul_c", "confidence": 0.7, "reason": "wind alignment"}
                ],
                evidence_fields={},
                confidence=0.7,
                model_version="source_attribution_rules_v0.1.0",
            )
        )
    seed_default_interventions(session)
    session.flush()


def test_generate_persists_with_safety_fields(session: Session) -> None:
    _seed(session)
    rec = generate_recommendation(
        session=session, target_zone_id="haul_c", now=T0
    )
    assert rec.recommendation_id.startswith("REC-20260501-")
    assert rec.confidence > 0
    assert rec.reason  # G3
    assert rec.model_version.startswith("optimization_weighted_")
    assert rec.linked_prediction_ids == ["PRED-20260501-0001"]
    assert rec.feature_pipeline_version == "features_v0.1.0"
    assert rec.input_data_quality_score == 0.9
    assert rec.automation_level == "L1"


def test_top_action_is_lowest_cost_effective(session: Session) -> None:
    _seed(session)
    rec = generate_recommendation(
        session=session, target_zone_id="haul_c", now=T0
    )
    # Haul-road catalog under balanced regime should pick water_road
    # (cheapest meaningful breach reduction).
    assert rec.recommended_actions
    assert rec.recommended_actions[0].intervention_id == "water_road"


def test_compliance_priority_surfaces_in_reason_under_extreme_breach(
    session: Session,
) -> None:
    _seed(session, breach_probability=0.92)
    rec = generate_recommendation(
        session=session, target_zone_id="haul_c", now=T0
    )
    assert rec.compliance_priority_triggered is True
    assert "compliance" in rec.reason.lower()


def test_low_confidence_drops_high_risk_actions(session: Session) -> None:
    _seed(session)
    # Knock confidence down by setting low_confidence_threshold high.
    cfg = next(iter(session.query(SiteConfiguration).all()))
    cfg.low_confidence_threshold = 0.99
    session.flush()

    rec = generate_recommendation(
        session=session, target_zone_id="haul_c", now=T0
    )
    assert rec.requires_human_review is True
    surfaced_classes = {a.risk_class for a in rec.recommended_actions}
    assert "medium" not in surfaced_classes
    assert "high" not in surfaced_classes


def test_attribution_linked_when_present(session: Session) -> None:
    _seed(session, with_attribution=True)
    rec = generate_recommendation(
        session=session, target_zone_id="haul_c", now=T0
    )
    assert rec.linked_attribution_id == "ATTR-20260501-001"


def test_attribution_null_when_absent(session: Session) -> None:
    _seed(session, with_attribution=False)
    rec = generate_recommendation(
        session=session, target_zone_id="haul_c", now=T0
    )
    assert rec.linked_attribution_id is None


def test_unknown_zone_raises(session: Session) -> None:
    _seed(session)
    with pytest.raises(ZoneNotFoundError):
        generate_recommendation(
            session=session, target_zone_id="ghost", now=T0
        )


def test_no_forecast_raises(session: Session) -> None:
    registry.reset()
    session.add(Mine(mine_id="m1", name="Demo"))
    session.add(
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
        generate_recommendation(
            session=session, target_zone_id="haul_c", now=T0
        )


def test_persisted_row_round_trips(session: Session) -> None:
    _seed(session)
    rec = generate_recommendation(
        session=session, target_zone_id="haul_c", now=T0
    )
    from app.storage.repositories.recommendations import RecommendationRepository

    row = RecommendationRepository(session).get(rec.recommendation_id)
    assert row is not None
    assert row.recommended_actions  # JSON round-tripped
    assert row.linked_prediction_ids == ["PRED-20260501-0001"]
