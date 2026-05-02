"""End-to-end training pipeline integration test (Phase L.6).

Proves that data flows all the way from raw readings through the K.1
S14 outcome-join into a persisted `model_performance_metrics` row —
the moment the K.1 scoreboard becomes load-bearing for any future
model calibration work.

Pipeline exercised:

  mock generators (synthetic SINCA-shape) ->
  DustPrediction (issued from heuristic feature pipeline) ->
  Recommendation + RecommendationApproval ->
  ActionOutcome ->
  load_and_assemble (K.1) ->
  compute_metric_payload (K.1) ->
  ModelPerformanceMetric row persisted

This is the "first metrics row" deliverable for Phase L.6. When real
SINCA / Los Pelambres data flows in, this same pipeline produces
real metrics rows without code changes — only the source records
change.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.domain.model_performance import compute_metric_payload
from app.domain.training_data import load_and_assemble
from app.storage.models import (
    ActionOutcome,
    DustPrediction,
    ModelPerformanceMetric,
    Recommendation,
    RecommendationApproval,
)
from app.storage.repositories.model_performance import (
    ModelPerformanceMetricRepository,
)


def _seed_one_loop(
    session: Session,
    *,
    issued_at: datetime,
    pm10_predicted: float,
    breach_prob: float,
    pm10_actual: float,
    breach_actual: bool,
    rec_id: str,
    pred_id: str,
    appr_id: str,
) -> None:
    session.add_all(
        [
            DustPrediction(
                prediction_id=pred_id,
                issued_at=issued_at,
                target_kind="zone",
                target_id="cuncumen-zone",
                forecast_horizon="30m",
                predicted_pm10=pm10_predicted,
                predicted_pm25=pm10_predicted * 0.35,
                breach_probability=breach_prob,
                confidence=0.6,
                main_risk_window="30m",
                main_uncertainty="andean drainage flow",
                model_version="dust_forecast_heuristic_v0.1.0",
                feature_pipeline_version="fp-0.1",
                input_data_quality_score=0.9,
                data_quality_warnings=[],
                source="orchestrator",
                input_record_ids=[],
            ),
            Recommendation(
                recommendation_id=rec_id,
                issued_at=issued_at + timedelta(minutes=1),
                target_zone_id="cuncumen-zone",
                risk_event="dust",
                current_breach_probability=breach_prob,
                target_probability=0.3,
                recommended_actions=[],
                requires_human_review=True,
                compliance_priority_triggered=False,
                confidence=0.6,
                reason="wind aligned with Cuncumén receptor",
                model_version="optimization_weighted_v0.1.0",
                feature_pipeline_version="fp-0.1",
                input_data_quality_score=0.9,
                data_quality_warnings=[],
                linked_prediction_ids=[pred_id],
                linked_attribution_id=None,
                automation_level="L1",
            ),
            RecommendationApproval(
                approval_id=appr_id,
                recommendation_id=rec_id,
                approved_by="alice",
                approver_role="environmental_manager",
                decided_at=issued_at + timedelta(minutes=5),
                approval_status="approved",
                chosen_action_rank=1,
                override_action=None,
                human_reason=None,
                automation_level_at_decision="L1",
            ),
            ActionOutcome(
                recommendation_id=rec_id,
                prediction_id=None,
                actual_pm10_peak=pm10_actual,
                actual_pm25_peak=pm10_actual * 0.32,
                breach_occurred=breach_actual,
                production_loss_tonnes_actual=120.0,
                intervention_effectiveness=(
                    "successful" if not breach_actual else "partial"
                ),
                model_error="ok",
                recorded_at=issued_at + timedelta(minutes=30),
                recorded_by="alice",
            ),
        ]
    )


def test_full_pipeline_produces_persisted_metric_row(session: Session) -> None:
    base = datetime(2026, 5, 1, 10, 0)
    # Three loops: 2 TPs, 1 TN.
    _seed_one_loop(
        session,
        issued_at=base,
        pm10_predicted=160.0,
        breach_prob=0.85,
        pm10_actual=158.0,
        breach_actual=True,
        rec_id="REC-LP-001",
        pred_id="PRED-LP-001",
        appr_id="APR-LP-001",
    )
    _seed_one_loop(
        session,
        issued_at=base + timedelta(minutes=15),
        pm10_predicted=140.0,
        breach_prob=0.70,
        pm10_actual=152.0,
        breach_actual=True,
        rec_id="REC-LP-002",
        pred_id="PRED-LP-002",
        appr_id="APR-LP-002",
    )
    _seed_one_loop(
        session,
        issued_at=base + timedelta(minutes=30),
        pm10_predicted=80.0,
        breach_prob=0.20,
        pm10_actual=78.0,
        breach_actual=False,
        rec_id="REC-LP-003",
        pred_id="PRED-LP-003",
        appr_id="APR-LP-003",
    )
    session.commit()

    # K.1 join + aggregator.
    records = load_and_assemble(
        session=session,
        window_from=base - timedelta(minutes=1),
        window_to=base + timedelta(minutes=45),
        now=base + timedelta(hours=2),
        observation_window=timedelta(minutes=60),
        model_version="dust_forecast_heuristic_v0.1.0",
    )
    assert len(records) == 3
    assert all(r.outcome_status == "observed" for r in records)

    payload = compute_metric_payload(records)
    assert payload["sample_count"] == 3
    assert payload["observed_count"] == 3
    # 2 TPs at >=0.5 breach prob; both real breaches -> precision 1.0
    assert payload["breach_precision"] == 1.0
    assert payload["breach_recall"] == 1.0

    # Persist the metric row — the L.6 deliverable.
    repo = ModelPerformanceMetricRepository(session)
    metric = ModelPerformanceMetric(
        model_version="dust_forecast_heuristic_v0.1.0",
        model_kind="dust_forecast",
        evaluated_at=base + timedelta(hours=2),
        window_from=base,
        window_to=base + timedelta(minutes=45),
        sample_count=payload["sample_count"],
        metric_payload=payload,
    )
    repo.add(metric)
    session.commit()

    persisted = repo.latest_for_version("dust_forecast_heuristic_v0.1.0")
    assert persisted is not None
    assert persisted.metric_payload["breach_precision"] == 1.0
    assert persisted.sample_count == 3
