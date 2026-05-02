"""Shadow-mode evaluation tests (Phase K.4)."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.domain.shadow_mode import evaluate_shadow
from app.storage.models import (
    ActionOutcome,
    DustPrediction,
    Recommendation,
    RecommendationApproval,
)


def _seed_pred(
    session: Session,
    *,
    pid: str,
    version: str,
    issued_at: datetime,
    breach_prob: float,
    actual_pm10: float,
    breach_actual: bool,
) -> None:
    pred = DustPrediction(
        prediction_id=pid,
        issued_at=issued_at,
        target_kind="zone",
        target_id="Z-1",
        forecast_horizon="30m",
        predicted_pm10=140.0,
        predicted_pm25=42.0,
        breach_probability=breach_prob,
        confidence=0.6,
        main_risk_window="30m",
        main_uncertainty="x",
        model_version=version,
        feature_pipeline_version="fp-0.1",
        input_data_quality_score=0.9,
        data_quality_warnings=[],
        source="orchestrator",
        input_record_ids=[],
    )
    rec = Recommendation(
        recommendation_id=f"REC-{pid}",
        issued_at=issued_at + timedelta(minutes=1),
        target_zone_id="Z-1",
        risk_event="dust",
        current_breach_probability=breach_prob,
        target_probability=0.3,
        recommended_actions=[],
        requires_human_review=True,
        compliance_priority_triggered=False,
        confidence=0.6,
        reason="x",
        model_version="oa-0.1.0",
        feature_pipeline_version="fp-0.1",
        input_data_quality_score=0.9,
        data_quality_warnings=[],
        linked_prediction_ids=[pid],
        linked_attribution_id=None,
        automation_level="L1",
    )
    appr = RecommendationApproval(
        approval_id=f"APR-{pid}",
        recommendation_id=f"REC-{pid}",
        approved_by="alice",
        approver_role="environmental_manager",
        decided_at=issued_at + timedelta(minutes=2),
        approval_status="approved",
        chosen_action_rank=1,
        override_action=None,
        human_reason=None,
        automation_level_at_decision="L1",
    )
    outcome = ActionOutcome(
        recommendation_id=f"REC-{pid}",
        prediction_id=None,
        actual_pm10_peak=actual_pm10,
        actual_pm25_peak=None,
        breach_occurred=breach_actual,
        production_loss_tonnes_actual=10.0,
        intervention_effectiveness="successful" if not breach_actual else "partial",
        model_error="ok",
        recorded_at=issued_at + timedelta(minutes=20),
        recorded_by="alice",
    )
    session.add_all([pred, rec, appr, outcome])


def test_promote_when_candidate_dominates(session: Session) -> None:
    base = datetime(2026, 5, 1, 10, 0)
    # Production: 1 TP, 1 FN -> recall 0.5
    _seed_pred(
        session,
        pid="P-PROD-1",
        version="prod-v1",
        issued_at=base,
        breach_prob=0.9,
        actual_pm10=160,
        breach_actual=True,
    )
    _seed_pred(
        session,
        pid="P-PROD-2",
        version="prod-v1",
        issued_at=base + timedelta(minutes=10),
        breach_prob=0.2,
        actual_pm10=170,
        breach_actual=True,
    )
    # Candidate: 2 TPs -> recall 1.0, MAE much lower
    _seed_pred(
        session,
        pid="P-CAND-1",
        version="cand-v2",
        issued_at=base,
        breach_prob=0.9,
        actual_pm10=160,
        breach_actual=True,
    )
    _seed_pred(
        session,
        pid="P-CAND-2",
        version="cand-v2",
        issued_at=base + timedelta(minutes=10),
        breach_prob=0.85,
        actual_pm10=170,
        breach_actual=True,
    )
    session.commit()

    result = evaluate_shadow(
        session=session,
        candidate_version="cand-v2",
        production_version="prod-v1",
        window_from=base - timedelta(minutes=1),
        window_to=base + timedelta(minutes=15),
        now=base + timedelta(hours=1),
        observation_window=timedelta(minutes=15),
    )
    assert result.recommendation == "promote"
    assert result.candidate_metrics["breach_recall"] == 1.0


def test_regress_when_candidate_misses_breaches(session: Session) -> None:
    base = datetime(2026, 5, 1, 10, 0)
    # Production: catches breach
    _seed_pred(
        session,
        pid="P-PROD-1",
        version="prod-v1",
        issued_at=base,
        breach_prob=0.9,
        actual_pm10=160,
        breach_actual=True,
    )
    # Candidate: misses it
    _seed_pred(
        session,
        pid="P-CAND-1",
        version="cand-v2",
        issued_at=base,
        breach_prob=0.2,
        actual_pm10=160,
        breach_actual=True,
    )
    session.commit()

    result = evaluate_shadow(
        session=session,
        candidate_version="cand-v2",
        production_version="prod-v1",
        window_from=base - timedelta(minutes=1),
        window_to=base + timedelta(minutes=10),
        now=base + timedelta(hours=1),
        observation_window=timedelta(minutes=15),
    )
    assert result.recommendation == "regress"


def test_hold_when_no_observations(session: Session) -> None:
    base = datetime(2026, 5, 1, 10, 0)
    # Both versions present but no outcomes -> nothing observed.
    pred1 = DustPrediction(
        prediction_id="P-X-1",
        issued_at=base,
        target_kind="zone",
        target_id="Z-1",
        forecast_horizon="30m",
        predicted_pm10=120.0,
        predicted_pm25=42.0,
        breach_probability=0.6,
        confidence=0.6,
        main_risk_window="30m",
        main_uncertainty="x",
        model_version="cand-v2",
        feature_pipeline_version="fp-0.1",
        input_data_quality_score=0.9,
        data_quality_warnings=[],
        source="orchestrator",
        input_record_ids=[],
    )
    pred2 = DustPrediction(
        prediction_id="P-X-2",
        issued_at=base,
        target_kind="zone",
        target_id="Z-1",
        forecast_horizon="30m",
        predicted_pm10=120.0,
        predicted_pm25=42.0,
        breach_probability=0.6,
        confidence=0.6,
        main_risk_window="30m",
        main_uncertainty="x",
        model_version="prod-v1",
        feature_pipeline_version="fp-0.1",
        input_data_quality_score=0.9,
        data_quality_warnings=[],
        source="orchestrator",
        input_record_ids=[],
    )
    session.add_all([pred1, pred2])
    session.commit()

    # observation window 5 min, "now" 1 min after base -> still within window,
    # so outcome_status="unobserved", observed_count=0 -> hold.
    result = evaluate_shadow(
        session=session,
        candidate_version="cand-v2",
        production_version="prod-v1",
        window_from=base - timedelta(minutes=1),
        window_to=base + timedelta(minutes=10),
        now=base + timedelta(minutes=1),
        observation_window=timedelta(minutes=5),
    )
    assert result.recommendation == "hold"
