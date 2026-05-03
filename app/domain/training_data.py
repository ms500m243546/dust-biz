"""S14 - Feedback and Learning Loop (Phase K).

Joins predictions × recommendations × approvals × outcomes into the
canonical `TrainingRecord` shape from
docs/subsystem-contracts.md S14.

The join is left-anchored on `DustPrediction`. A prediction may have:
- no recommendation (forecast did not breach the trigger threshold);
- a recommendation but no approval row yet (rare; the orchestrator
  always records an approval, even auto-expired);
- a recommendation + approval but no outcome yet — these are emitted
  with `outcome_status="unobserved"` past the configured observation
  window, per the S14 failure mode.

Pure domain function: takes pre-loaded rows, returns Pydantic models.
The route handler is responsible for the queries and time-window
config; this module is testable without a database session.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.schemas.model_performance import TrainingRecordSchema
from app.storage.models import (
    ActionOutcome,
    DustPrediction,
    Recommendation,
    RecommendationApproval,
)

LoadMode = Literal["training_feature", "evaluation"]


@dataclass(frozen=True)
class _OutcomeBucket:
    """One outcome row, indexed for cheap lookup by either FK."""

    by_recommendation_id: dict[str, ActionOutcome]
    by_prediction_id: dict[str, ActionOutcome]


def _index_outcomes(rows: Iterable[ActionOutcome]) -> _OutcomeBucket:
    by_rec: dict[str, ActionOutcome] = {}
    by_pred: dict[str, ActionOutcome] = {}
    for r in rows:
        # Latest-wins: outcomes are append-only, but if a rec/pred has
        # multiple outcome rows we keep the most recent one.
        if r.recommendation_id is not None:
            existing = by_rec.get(r.recommendation_id)
            if existing is None or r.recorded_at > existing.recorded_at:
                by_rec[r.recommendation_id] = r
        if r.prediction_id is not None:
            existing = by_pred.get(r.prediction_id)
            if existing is None or r.recorded_at > existing.recorded_at:
                by_pred[r.prediction_id] = r
    return _OutcomeBucket(by_rec, by_pred)


def _latest_approval_for(
    approvals: Iterable[RecommendationApproval], recommendation_id: str
) -> RecommendationApproval | None:
    latest: RecommendationApproval | None = None
    for a in approvals:
        if a.recommendation_id != recommendation_id:
            continue
        if latest is None or a.decided_at > latest.decided_at:
            latest = a
    return latest


def _recommendation_for_prediction(
    recommendations: Iterable[Recommendation], prediction_id: str
) -> Recommendation | None:
    """Return the latest recommendation that links to this prediction.

    `Recommendation.linked_prediction_ids` is a JSON list; we scan in
    Python because SQLite can't index JSON membership efficiently. The
    caller is expected to pass a list narrowed to the prediction
    window so this stays cheap.
    """
    latest: Recommendation | None = None
    for rec in recommendations:
        if prediction_id not in (rec.linked_prediction_ids or []):
            continue
        if latest is None or rec.issued_at > latest.issued_at:
            latest = rec
    return latest


def _build_record(
    prediction: DustPrediction,
    recommendation: Recommendation | None,
    approval: RecommendationApproval | None,
    outcome: ActionOutcome | None,
    *,
    now: datetime,
    observation_window: timedelta,
) -> TrainingRecordSchema:
    if outcome is not None:
        outcome_status = "observed"
    elif now - prediction.issued_at >= observation_window:
        outcome_status = "unobserved"
    else:
        # Still within the observation window — too early to call
        # this one unobserved. We still emit it (caller may filter)
        # so dashboards can show "in flight" predictions.
        outcome_status = "unobserved"

    if recommendation is None:
        human_action: str = "no_recommendation"
    elif approval is None:
        human_action = "expired"
    else:
        human_action = approval.approval_status

    return TrainingRecordSchema(
        prediction_id=prediction.prediction_id,
        recommendation_id=(
            recommendation.recommendation_id if recommendation else None
        ),
        approval_id=approval.approval_id if approval else None,
        outcome_id=outcome.outcome_id if outcome else None,
        issued_at=prediction.issued_at,
        target_kind=prediction.target_kind,
        target_id=prediction.target_id,
        forecast_horizon=prediction.forecast_horizon,
        predicted_pm10=prediction.predicted_pm10,
        predicted_pm25=prediction.predicted_pm25,
        predicted_breach_probability=prediction.breach_probability,
        confidence=prediction.confidence,
        model_version=prediction.model_version,
        human_action=human_action,  # type: ignore[arg-type]
        chosen_action_rank=approval.chosen_action_rank if approval else None,
        override_action=approval.override_action if approval else None,
        actual_pm10_peak=outcome.actual_pm10_peak if outcome else None,
        actual_pm25_peak=outcome.actual_pm25_peak if outcome else None,
        breach_occurred=outcome.breach_occurred if outcome else None,
        intervention_effectiveness=(
            outcome.intervention_effectiveness if outcome else None  # type: ignore[arg-type]
        ),
        production_loss_tonnes_actual=(
            outcome.production_loss_tonnes_actual if outcome else None
        ),
        model_error=outcome.model_error if outcome else None,
        outcome_status=outcome_status,  # type: ignore[arg-type]
        recorded_at=outcome.recorded_at if outcome else None,
    )


def assemble_training_records(
    *,
    predictions: Iterable[DustPrediction],
    recommendations: Iterable[Recommendation],
    approvals: Iterable[RecommendationApproval],
    outcomes: Iterable[ActionOutcome],
    now: datetime,
    observation_window: timedelta = timedelta(minutes=180),
) -> list[TrainingRecordSchema]:
    """Pure join. Caller pre-loads the four entity sets."""
    rec_list = list(recommendations)
    appr_list = list(approvals)
    outcome_index = _index_outcomes(outcomes)

    out: list[TrainingRecordSchema] = []
    for pred in predictions:
        rec = _recommendation_for_prediction(rec_list, pred.prediction_id)
        approval = (
            _latest_approval_for(appr_list, rec.recommendation_id)
            if rec is not None
            else None
        )
        outcome = (
            outcome_index.by_recommendation_id.get(rec.recommendation_id)
            if rec is not None
            else None
        )
        if outcome is None:
            outcome = outcome_index.by_prediction_id.get(pred.prediction_id)
        out.append(
            _build_record(
                pred,
                rec,
                approval,
                outcome,
                now=now,
                observation_window=observation_window,
            )
        )
    return out


def load_and_assemble(
    *,
    session: Session,
    window_from: datetime,
    window_to: datetime,
    now: datetime,
    observation_window: timedelta = timedelta(minutes=180),
    model_version: str | None = None,
    mode: LoadMode = "evaluation",
) -> list[TrainingRecordSchema]:
    """Convenience: query the four tables for the window and assemble.

    M.2 `mode`:
    - `"evaluation"` (default): full ground truth — every label in the
      window participates regardless of `labeled_at`. This is correct
      for S14's intended job: measuring what *actually happened* after
      a prediction fired. Outcomes by definition occur after their
      prediction; filtering them by `labeled_at <= issued_at` would
      defeat the point of the join.
    - `"training_feature"`: PIT-filtered. Use when consuming labels
      as *training features* for a new model — i.e., the future S5
      feature-engineering caller. For each prediction `p`, only labels
      with `labeled_at <= p.issued_at` are eligible (anti-hindsight
      rule 3). Use this mode only when training a model that takes
      labels as features at decision-time.

    The default is `"evaluation"` because every existing caller (S14
    audit, S15 reports, shadow-mode comparisons, model_performance
    aggregation) is doing evaluation, not feature engineering. The
    PIT enforcement for *training* lives upstream at the feature
    pipeline (S5; not yet implemented), where it's the right layer.
    """
    pred_stmt = (
        select(DustPrediction)
        .where(DustPrediction.issued_at >= window_from)
        .where(DustPrediction.issued_at <= window_to)
        .order_by(DustPrediction.issued_at.asc())
    )
    if model_version is not None:
        pred_stmt = pred_stmt.where(DustPrediction.model_version == model_version)
    predictions = list(session.execute(pred_stmt).scalars())

    rec_stmt = (
        select(Recommendation)
        .where(Recommendation.issued_at >= window_from)
        .where(Recommendation.issued_at <= window_to + observation_window)
    )
    recommendations = list(session.execute(rec_stmt).scalars())

    appr_stmt = (
        select(RecommendationApproval)
        .where(RecommendationApproval.decided_at >= window_from)
        .where(RecommendationApproval.decided_at <= window_to + observation_window)
    )
    approvals = list(session.execute(appr_stmt).scalars())

    outcome_stmt = (
        select(ActionOutcome)
        .where(ActionOutcome.recorded_at >= window_from)
        .where(ActionOutcome.recorded_at <= window_to + observation_window)
    )
    outcomes = list(session.execute(outcome_stmt).scalars())

    if mode == "training_feature":
        # PIT-filter labels. Callers consuming labels as training
        # features for a new model must restrict to labels knowable
        # at the *earliest* prediction in the window (i.e., labels
        # that pre-date even the first prediction `p` for which they'd
        # be features). Conservative cut: drop labels with
        # labeled_at > earliest_issued.
        earliest_issued = min(
            (p.issued_at for p in predictions), default=window_from
        )
        recommendations = [
            r for r in recommendations if r.labeled_at <= earliest_issued
        ]
        approvals = [a for a in approvals if a.labeled_at <= earliest_issued]
        outcomes = [o for o in outcomes if o.labeled_at <= earliest_issued]

    return assemble_training_records(
        predictions=predictions,
        recommendations=recommendations,
        approvals=approvals,
        outcomes=outcomes,
        now=now,
        observation_window=observation_window,
    )


__all__ = [
    "assemble_training_records",
    "load_and_assemble",
]
