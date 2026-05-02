"""ActionOutcome repository tests (Phase I)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.storage.models import ActionOutcome
from app.storage.repositories.outcomes import ActionOutcomeRepository


def test_add_and_query(session: Session) -> None:
    repo = ActionOutcomeRepository(session)
    repo.add(
        ActionOutcome(
            recommendation_id=None,
            prediction_id=None,
            actual_pm10_peak=110.0,
            actual_pm25_peak=40.0,
            breach_occurred=False,
            production_loss_tonnes_actual=200.0,
            intervention_effectiveness="successful",
            model_error="overpredicted by 11%",
            recorded_at=datetime(2026, 5, 1, 13, 0, 0),
            recorded_by="bob",
        )
    )
    session.commit()

    rows = repo.get_recent(since=datetime(2026, 5, 1, 0, 0))
    assert len(rows) == 1
    assert rows[0].intervention_effectiveness == "successful"
