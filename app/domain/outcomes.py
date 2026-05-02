"""Outcome capture (Phase I, S14 feeder).

Manual entry path: an environmental manager or operations manager logs
the actual PM10 peak, whether a breach occurred, and how effective the
intervention was. The Phase K join (S14) reads these rows and computes
predicted-vs-actual error.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.audit import record as audit_record
from app.schemas.outcomes import ActionOutcomeCreate, ActionOutcomeSchema
from app.storage.models import ActionOutcome, DustPrediction, Recommendation
from app.storage.repositories.outcomes import ActionOutcomeRepository


class UnknownRecommendationError(Exception):
    pass


class UnknownPredictionError(Exception):
    pass


def record_outcome(
    *,
    session: Session,
    payload: ActionOutcomeCreate,
    actor_username: str,
    now: datetime | None = None,
) -> ActionOutcomeSchema:
    if (
        payload.recommendation_id is not None
        and session.get(Recommendation, payload.recommendation_id) is None
    ):
        raise UnknownRecommendationError(
            f"unknown recommendation_id: {payload.recommendation_id}"
        )
    if (
        payload.prediction_id is not None
        and session.get(DustPrediction, payload.prediction_id) is None
    ):
        raise UnknownPredictionError(
            f"unknown prediction_id: {payload.prediction_id}"
        )

    moment = (now or datetime.now(UTC)).replace(microsecond=0)
    if moment.tzinfo is not None:
        moment = moment.replace(tzinfo=None)

    row = ActionOutcome(
        recommendation_id=payload.recommendation_id,
        prediction_id=payload.prediction_id,
        actual_pm10_peak=payload.actual_pm10_peak,
        actual_pm25_peak=payload.actual_pm25_peak,
        breach_occurred=payload.breach_occurred,
        production_loss_tonnes_actual=payload.production_loss_tonnes_actual,
        intervention_effectiveness=payload.intervention_effectiveness,
        model_error=payload.model_error,
        recorded_at=moment,
        recorded_by=actor_username,
    )
    persisted = ActionOutcomeRepository(session).add(row)

    entity_id = (
        payload.recommendation_id
        or payload.prediction_id
        or f"outcome-{persisted.outcome_id}"
    )
    audit_record(
        session,
        actor=actor_username,
        action="record_outcome",
        entity_type="recommendation" if payload.recommendation_id else "prediction",
        entity_id=entity_id,
        payload={
            "outcome_id": persisted.outcome_id,
            "actual_pm10_peak": payload.actual_pm10_peak,
            "breach_occurred": payload.breach_occurred,
            "intervention_effectiveness": payload.intervention_effectiveness,
        },
        occurred_at=moment,
    )
    return ActionOutcomeSchema.model_validate(persisted)


__all__ = [
    "UnknownPredictionError",
    "UnknownRecommendationError",
    "record_outcome",
]
