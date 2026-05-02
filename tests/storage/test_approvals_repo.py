"""RecommendationApproval repository tests (Phase I)."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.storage.models import Recommendation, RecommendationApproval
from app.storage.repositories.approvals import RecommendationApprovalRepository


def _seed_recommendation(session: Session, rec_id: str = "REC-20260501-00001") -> None:
    session.add(
        Recommendation(
            recommendation_id=rec_id,
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


def test_add_and_latest(session: Session) -> None:
    _seed_recommendation(session)
    repo = RecommendationApprovalRepository(session)

    repo.add(
        RecommendationApproval(
            approval_id="APR-20260501-00001",
            recommendation_id="REC-20260501-00001",
            approved_by="alice",
            approver_role="shift_supervisor",
            decided_at=datetime(2026, 5, 1, 12, 5, 0),
            approval_status="approved",
            chosen_action_rank=1,
            override_action=None,
            human_reason=None,
            automation_level_at_decision="L1",
        )
    )
    repo.add(
        RecommendationApproval(
            approval_id="APR-20260501-00002",
            recommendation_id="REC-20260501-00001",
            approved_by="bob",
            approver_role="environmental_manager",
            decided_at=datetime(2026, 5, 1, 12, 10, 0),
            approval_status="overridden",
            chosen_action_rank=None,
            override_action="hold trucks 5min",
            human_reason="dust plume already visible",
            automation_level_at_decision="L1",
        )
    )
    session.commit()

    latest = repo.latest_for_recommendation("REC-20260501-00001")
    assert latest is not None
    assert latest.approval_status == "overridden"

    recent = repo.get_recent(since=datetime(2026, 5, 1, 0, 0, 0))
    assert len(recent) == 2
    assert recent[0].decided_at > recent[1].decided_at


def test_next_approval_id_increments(session: Session) -> None:
    _seed_recommendation(session)
    repo = RecommendationApprovalRepository(session)
    on_date = datetime(2026, 5, 1)
    assert repo.next_approval_id(on_date) == "APR-20260501-00001"
    repo.add(
        RecommendationApproval(
            approval_id="APR-20260501-00001",
            recommendation_id="REC-20260501-00001",
            approved_by="alice",
            approver_role="shift_supervisor",
            decided_at=on_date + timedelta(minutes=5),
            approval_status="approved",
            chosen_action_rank=1,
            override_action=None,
            human_reason=None,
            automation_level_at_decision="L1",
        )
    )
    session.commit()
    assert repo.next_approval_id(on_date) == "APR-20260501-00002"
