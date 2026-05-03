"""Phase R.2 — intervention calibration tests."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.storage.models import (
    ActionOutcome,
    Base,
    Recommendation,
    RecommendationApproval,
)
from app.training.intervention_validation import (
    MIN_OUTCOMES_FOR_CALIBRATION,
    SANITY_BAND_LOWER,
    SANITY_BAND_UPPER,
    validate_intervention_calibration,
)


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    with SessionLocal() as s:
        yield s


def _add_outcome(
    session: Session,
    *,
    rec_id: str,
    actual: float,
    breach: bool,
) -> None:
    session.add(
        Recommendation(
            recommendation_id=rec_id,
            issued_at=datetime(2026, 4, 1),
            target_zone_id="z",
            risk_event="elevated",
            current_breach_probability=0.6,
            target_probability=0.3,
            requires_human_review=True,
            compliance_priority_triggered=False,
            confidence=0.7,
            reason="test",
            model_version="rec_v0.1",
            feature_pipeline_version="fp_v0.1",
            input_data_quality_score=0.9,
            data_quality_warnings=[],
            linked_prediction_ids=[],
            automation_level="L1",
        )
    )
    session.add(
        RecommendationApproval(
            approval_id=f"appr-{rec_id}",
            recommendation_id=rec_id,
            approved_by="op",
            approver_role="shift_supervisor",
            decided_at=datetime(2026, 4, 1, 1, 0),
            approval_status="approved",
            chosen_action_rank=1,
            human_reason=None,
            automation_level_at_decision="L1",
        )
    )
    session.add(
        ActionOutcome(
            recommendation_id=rec_id,
            actual_pm10_peak=actual,
            breach_occurred=breach,
            intervention_effectiveness="successful" if not breach else "partial",
            recorded_at=datetime(2026, 4, 1, 2, 0),
            recorded_by="op",
        )
    )
    session.flush()


def test_calibration_deferred_when_no_outcomes(session: Session) -> None:
    report = validate_intervention_calibration(session)
    assert report.status == "deferred"
    assert report.joined_row_count == 0
    assert report.sample_warning is not None


def test_calibration_deferred_below_minimum(session: Session) -> None:
    for i in range(5):
        _add_outcome(session, rec_id=f"r{i}", actual=120.0, breach=False)
    report = validate_intervention_calibration(session)
    assert report.status == "deferred"
    assert report.joined_row_count == 5
    assert report.joined_row_count < MIN_OUTCOMES_FOR_CALIBRATION


def test_calibration_calibrated_at_threshold(session: Session) -> None:
    for i in range(MIN_OUTCOMES_FOR_CALIBRATION):
        _add_outcome(session, rec_id=f"r{i}", actual=140.0, breach=False)
    report = validate_intervention_calibration(session)
    assert report.status == "calibrated"
    assert report.joined_row_count == MIN_OUTCOMES_FOR_CALIBRATION


def test_sanity_band_constants_are_in_unit_interval() -> None:
    assert 0.0 <= SANITY_BAND_LOWER < SANITY_BAND_UPPER <= 1.0
