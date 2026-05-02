"""Outcome capture domain tests (Phase I)."""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from app.domain.outcomes import (
    UnknownPredictionError,
    UnknownRecommendationError,
    record_outcome,
)
from app.schemas.outcomes import ActionOutcomeCreate
from app.storage.models import Recommendation


def _seed_rec(session: Session) -> None:
    session.add(
        Recommendation(
            recommendation_id="REC-1",
            issued_at=datetime(2026, 5, 1, 12, 0, 0),
            target_zone_id="Z1",
            risk_event="r",
            current_breach_probability=0.6,
            target_probability=0.25,
            recommended_actions=[],
            requires_human_review=False,
            compliance_priority_triggered=False,
            confidence=0.8,
            reason="r",
            model_version="m",
            feature_pipeline_version="f",
            input_data_quality_score=0.9,
            data_quality_warnings=[],
            linked_prediction_ids=[],
            linked_attribution_id=None,
            automation_level="L1",
            top_production_impact="low",
        )
    )
    session.commit()


def test_record_outcome_links_to_recommendation(session: Session) -> None:
    _seed_rec(session)
    out = record_outcome(
        session=session,
        payload=ActionOutcomeCreate(
            recommendation_id="REC-1",
            actual_pm10_peak=120.0,
            breach_occurred=False,
            intervention_effectiveness="successful",
        ),
        actor_username="bob",
        now=datetime(2026, 5, 1, 13, 0, 0),
    )
    session.commit()
    assert out.recommendation_id == "REC-1"
    assert out.intervention_effectiveness == "successful"

    from app.storage.repositories.audit import AuditLogRepository

    rows = AuditLogRepository(session).for_entity("recommendation", "REC-1")
    assert any(r.action == "record_outcome" for r in rows)


def test_unknown_recommendation_raises(session: Session) -> None:
    with pytest.raises(UnknownRecommendationError):
        record_outcome(
            session=session,
            payload=ActionOutcomeCreate(
                recommendation_id="REC-MISSING",
                actual_pm10_peak=120.0,
                breach_occurred=False,
                intervention_effectiveness="not_applicable",
            ),
            actor_username="bob",
        )


def test_unknown_prediction_raises(session: Session) -> None:
    with pytest.raises(UnknownPredictionError):
        record_outcome(
            session=session,
            payload=ActionOutcomeCreate(
                prediction_id="PRED-MISSING",
                actual_pm10_peak=120.0,
                breach_occurred=False,
                intervention_effectiveness="not_applicable",
            ),
            actor_username="bob",
        )


def test_unlinked_outcome_allowed(session: Session) -> None:
    out = record_outcome(
        session=session,
        payload=ActionOutcomeCreate(
            actual_pm10_peak=120.0,
            breach_occurred=True,
            intervention_effectiveness="not_applicable",
        ),
        actor_username="bob",
        now=datetime(2026, 5, 1, 13, 0, 0),
    )
    session.commit()
    assert out.recommendation_id is None
    assert out.prediction_id is None
