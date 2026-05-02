"""Approval orchestrator tests (Phase I, S13)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.domain.approvals import (
    AlreadyDecidedError,
    HighRiskAutoExecutionError,
    InvalidActionRankError,
    RecommendationNotFoundError,
    approve_recommendation,
    latest_for_recommendation,
    override_recommendation,
    reject_recommendation,
    sweep_expired,
)
from app.storage.models import Recommendation


def _seed_rec(
    session: Session,
    *,
    rec_id: str = "REC-20260501-00001",
    issued_at: datetime = datetime(2026, 5, 1, 12, 0, 0),
    actions: list[dict[str, Any]] | None = None,
    automation_level: str = "L1",
) -> Recommendation:
    actions = actions or [
        {
            "rank": 1,
            "intervention_id": "reduce_speed",
            "action": "Reduce speed",
            "breach_probability_after": 0.2,
            "production_loss": "low",
            "estimated_tonnes_delayed": 100.0,
            "confidence": 0.8,
            "reason": "ok",
            "requires_human_approval": True,
            "risk_class": "medium",
            "simulation_id": "SIM-1",
        },
    ]
    rec = Recommendation(
        recommendation_id=rec_id,
        issued_at=issued_at,
        target_zone_id="Z1",
        risk_event="r",
        current_breach_probability=0.7,
        target_probability=0.25,
        recommended_actions=actions,
        requires_human_review=False,
        compliance_priority_triggered=False,
        confidence=0.8,
        reason="r",
        model_version="optimization_weighted_v0.1.0",
        feature_pipeline_version="f",
        input_data_quality_score=0.9,
        data_quality_warnings=[],
        linked_prediction_ids=[],
        linked_attribution_id=None,
        automation_level=automation_level,
        top_production_impact="low",
    )
    session.add(rec)
    session.commit()
    return rec


def test_approve_records_decision_and_audit(session: Session) -> None:
    _seed_rec(session)
    out = approve_recommendation(
        session=session,
        recommendation_id="REC-20260501-00001",
        chosen_action_rank=1,
        human_reason="visible plume building",
        actor_username="alice",
        actor_role="shift_supervisor",
        now=datetime(2026, 5, 1, 12, 5, 0),
    )
    session.commit()

    assert out.approval_status == "approved"
    assert out.chosen_action_rank == 1
    assert out.approved_by == "alice"
    assert out.confidence == 0.8
    assert out.model_version == "optimization_weighted_v0.1.0"

    from app.storage.repositories.audit import AuditLogRepository

    audit = AuditLogRepository(session).for_entity(
        "recommendation", "REC-20260501-00001"
    )
    assert any(r.action == "approved_recommendation" for r in audit)


def test_reject_records_decision(session: Session) -> None:
    _seed_rec(session)
    out = reject_recommendation(
        session=session,
        recommendation_id="REC-20260501-00001",
        human_reason="ground-truth disagrees",
        actor_username="bob",
        actor_role="environmental_manager",
        now=datetime(2026, 5, 1, 12, 5, 0),
    )
    session.commit()
    assert out.approval_status == "rejected"
    assert out.chosen_action_rank is None
    assert out.human_reason == "ground-truth disagrees"


def test_override_records_decision(session: Session) -> None:
    _seed_rec(session)
    out = override_recommendation(
        session=session,
        recommendation_id="REC-20260501-00001",
        override_action="hold trucks 5min",
        human_reason="visible plume already present",
        actor_username="bob",
        actor_role="environmental_manager",
        now=datetime(2026, 5, 1, 12, 5, 0),
    )
    session.commit()
    assert out.approval_status == "overridden"
    assert out.override_action == "hold trucks 5min"


def test_already_decided_blocks_second_decision(session: Session) -> None:
    _seed_rec(session)
    approve_recommendation(
        session=session,
        recommendation_id="REC-20260501-00001",
        chosen_action_rank=1,
        human_reason=None,
        actor_username="alice",
        actor_role="shift_supervisor",
        now=datetime(2026, 5, 1, 12, 5, 0),
    )
    session.commit()
    with pytest.raises(AlreadyDecidedError):
        reject_recommendation(
            session=session,
            recommendation_id="REC-20260501-00001",
            human_reason="changed my mind",
            actor_username="alice",
            actor_role="shift_supervisor",
            now=datetime(2026, 5, 1, 12, 6, 0),
        )


def test_unknown_recommendation_404s(session: Session) -> None:
    with pytest.raises(RecommendationNotFoundError):
        approve_recommendation(
            session=session,
            recommendation_id="REC-MISSING",
            chosen_action_rank=1,
            human_reason=None,
            actor_username="alice",
            actor_role="shift_supervisor",
        )


def test_invalid_rank_422s(session: Session) -> None:
    _seed_rec(session)
    with pytest.raises(InvalidActionRankError):
        approve_recommendation(
            session=session,
            recommendation_id="REC-20260501-00001",
            chosen_action_rank=99,
            human_reason=None,
            actor_username="alice",
            actor_role="shift_supervisor",
            now=datetime(2026, 5, 1, 12, 5, 0),
        )


def test_high_risk_blocked_from_approve_path(session: Session) -> None:
    _seed_rec(
        session,
        actions=[
            {
                "rank": 1,
                "intervention_id": "stop_blast",
                "action": "Stop scheduled blast",
                "breach_probability_after": 0.05,
                "production_loss": "high",
                "estimated_tonnes_delayed": 5000.0,
                "confidence": 0.7,
                "reason": "critical",
                "requires_human_approval": True,
                "risk_class": "high",
                "simulation_id": "SIM-2",
            },
        ],
    )
    with pytest.raises(HighRiskAutoExecutionError):
        approve_recommendation(
            session=session,
            recommendation_id="REC-20260501-00001",
            chosen_action_rank=1,
            human_reason=None,
            actor_username="alice",
            actor_role="shift_supervisor",
            now=datetime(2026, 5, 1, 12, 5, 0),
        )


def test_lazy_expiry_records_expired_status(session: Session) -> None:
    _seed_rec(session)
    out = approve_recommendation(
        session=session,
        recommendation_id="REC-20260501-00001",
        chosen_action_rank=1,
        human_reason=None,
        actor_username="alice",
        actor_role="shift_supervisor",
        # 30 minutes after issuance, default expiry is 15 min
        now=datetime(2026, 5, 1, 12, 30, 0),
    )
    session.commit()
    assert out.approval_status == "expired"


def test_sweep_expired_finds_pending_recommendations(session: Session) -> None:
    _seed_rec(session)
    out = sweep_expired(
        session=session,
        now=datetime(2026, 5, 1, 13, 0, 0),
    )
    session.commit()
    assert len(out) == 1
    assert out[0].approval_status == "expired"


def test_latest_for_recommendation_returns_decision(session: Session) -> None:
    _seed_rec(session)
    assert latest_for_recommendation(
        session=session, recommendation_id="REC-20260501-00001"
    ) is None

    approve_recommendation(
        session=session,
        recommendation_id="REC-20260501-00001",
        chosen_action_rank=1,
        human_reason=None,
        actor_username="alice",
        actor_role="shift_supervisor",
        now=datetime(2026, 5, 1, 12, 5, 0),
    )
    session.commit()
    latest = latest_for_recommendation(
        session=session, recommendation_id="REC-20260501-00001"
    )
    assert latest is not None
    assert latest.approval_status == "approved"


def test_expiry_window_relative_to_issued_at(session: Session) -> None:
    issued = datetime(2026, 5, 1, 12, 0, 0)
    _seed_rec(session, issued_at=issued)
    # 14 minutes later: still in window
    out = approve_recommendation(
        session=session,
        recommendation_id="REC-20260501-00001",
        chosen_action_rank=1,
        human_reason=None,
        actor_username="alice",
        actor_role="shift_supervisor",
        now=issued + timedelta(minutes=14),
    )
    session.commit()
    assert out.approval_status == "approved"
