"""S14 training-data join tests (Phase K)."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.domain.training_data import assemble_training_records
from app.storage.models import (
    ActionOutcome,
    DustPrediction,
    Recommendation,
    RecommendationApproval,
)


def _pred(
    pid: str = "PRED-20260501-0001",
    issued_at: datetime = datetime(2026, 5, 1, 10, 0),
    breach: float = 0.74,
) -> DustPrediction:
    return DustPrediction(
        prediction_id=pid,
        issued_at=issued_at,
        target_kind="zone",
        target_id="Z-1",
        forecast_horizon="30m",
        predicted_pm10=120.0,
        predicted_pm25=42.0,
        breach_probability=breach,
        confidence=0.6,
        main_risk_window="30m",
        main_uncertainty="wind variability",
        model_version="df-0.1.0",
        feature_pipeline_version="fp-0.1",
        input_data_quality_score=0.9,
        data_quality_warnings=[],
        source="orchestrator",
        input_record_ids=[],
    )


def _rec(
    rid: str = "REC-20260501-00001",
    linked: list[str] | None = None,
    issued_at: datetime = datetime(2026, 5, 1, 10, 1),
) -> Recommendation:
    return Recommendation(
        recommendation_id=rid,
        issued_at=issued_at,
        target_zone_id="Z-1",
        risk_event="dust",
        current_breach_probability=0.74,
        target_probability=0.3,
        recommended_actions=[],
        requires_human_review=True,
        compliance_priority_triggered=False,
        confidence=0.6,
        reason="wind aligned with active loading",
        model_version="oa-0.1.0",
        feature_pipeline_version="fp-0.1",
        input_data_quality_score=0.9,
        data_quality_warnings=[],
        linked_prediction_ids=linked or ["PRED-20260501-0001"],
        linked_attribution_id=None,
        automation_level="L1",
    )


def _approval(
    rec_id: str = "REC-20260501-00001",
    decided_at: datetime = datetime(2026, 5, 1, 10, 5),
    status: str = "approved",
    aid: str = "APR-20260501-00001",
) -> RecommendationApproval:
    return RecommendationApproval(
        approval_id=aid,
        recommendation_id=rec_id,
        approved_by="alice",
        approver_role="environmental_manager",
        decided_at=decided_at,
        approval_status=status,
        chosen_action_rank=1,
        override_action=None,
        human_reason=None,
        automation_level_at_decision="L1",
    )


def _outcome(
    rec_id: str | None = "REC-20260501-00001",
    pred_id: str | None = None,
    actual_pm10: float = 119.0,
    breach_occurred: bool = False,
    recorded_at: datetime = datetime(2026, 5, 1, 13, 0),
) -> ActionOutcome:
    return ActionOutcome(
        recommendation_id=rec_id,
        prediction_id=pred_id,
        actual_pm10_peak=actual_pm10,
        actual_pm25_peak=None,
        breach_occurred=breach_occurred,
        production_loss_tonnes_actual=200.0,
        intervention_effectiveness="successful",
        model_error="overpredicted by 1%",
        recorded_at=recorded_at,
        recorded_by="alice",
    )


def test_full_join_produces_observed_record() -> None:
    records = assemble_training_records(
        predictions=[_pred()],
        recommendations=[_rec()],
        approvals=[_approval()],
        outcomes=[_outcome()],
        now=datetime(2026, 5, 1, 14, 0),
    )
    assert len(records) == 1
    r = records[0]
    assert r.outcome_status == "observed"
    assert r.human_action == "approved"
    assert r.actual_pm10_peak == 119.0
    assert r.recommendation_id == "REC-20260501-00001"
    assert r.approval_id == "APR-20260501-00001"


def test_prediction_without_recommendation_is_no_recommendation() -> None:
    records = assemble_training_records(
        predictions=[_pred()],
        recommendations=[],
        approvals=[],
        outcomes=[],
        now=datetime(2026, 5, 1, 14, 0),
    )
    assert len(records) == 1
    assert records[0].human_action == "no_recommendation"
    # Past observation window (4h elapsed, default 3h) -> unobserved
    assert records[0].outcome_status == "unobserved"


def test_outcome_within_window_still_unobserved_only_when_no_outcome() -> None:
    # Prediction issued 30 min ago, no outcome yet, within 3h window.
    records = assemble_training_records(
        predictions=[_pred(issued_at=datetime(2026, 5, 1, 13, 30))],
        recommendations=[_rec(issued_at=datetime(2026, 5, 1, 13, 31))],
        approvals=[_approval(decided_at=datetime(2026, 5, 1, 13, 35))],
        outcomes=[],
        now=datetime(2026, 5, 1, 14, 0),
    )
    assert records[0].outcome_status == "unobserved"
    assert records[0].human_action == "approved"


def test_outcome_indexed_by_prediction_id_when_no_recommendation() -> None:
    # An outcome can be filed against a prediction directly when no
    # recommendation was issued (the manual entry path).
    records = assemble_training_records(
        predictions=[_pred()],
        recommendations=[],
        approvals=[],
        outcomes=[_outcome(rec_id=None, pred_id="PRED-20260501-0001")],
        now=datetime(2026, 5, 1, 14, 0),
    )
    assert records[0].outcome_status == "observed"
    assert records[0].human_action == "no_recommendation"


def test_observation_window_override() -> None:
    records = assemble_training_records(
        predictions=[_pred(issued_at=datetime(2026, 5, 1, 13, 0))],
        recommendations=[],
        approvals=[],
        outcomes=[],
        now=datetime(2026, 5, 1, 14, 0),
        observation_window=timedelta(minutes=30),
    )
    assert records[0].outcome_status == "unobserved"
