"""Approval schema validation tests (Phase I)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from app.schemas.approvals import (
    ApproveRequest,
    OverrideRequest,
    RecommendationApprovalSchema,
    RejectRequest,
)


def _base(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "approval_id": "APR-1",
        "recommendation_id": "REC-1",
        "approved_by": "alice",
        "approver_role": "shift_supervisor",
        "decided_at": datetime(2026, 5, 1, 12, 0, 0),
        "approval_status": "approved",
        "chosen_action_rank": 1,
        "automation_level_at_decision": "L1",
        "confidence": 0.8,
        "reason": "approved by supervisor",
        "model_version": "optimization_weighted_v0.1.0",
    }
    base.update(overrides)
    return base


def test_approved_requires_chosen_action_rank() -> None:
    with pytest.raises(ValueError):
        RecommendationApprovalSchema(**_base(chosen_action_rank=None))


def test_overridden_requires_override_action() -> None:
    with pytest.raises(ValueError):
        RecommendationApprovalSchema(
            **_base(
                approval_status="overridden",
                chosen_action_rank=None,
                override_action=None,
                human_reason="x",
            )
        )


def test_rejected_allows_no_rank() -> None:
    s = RecommendationApprovalSchema(
        **_base(
            approval_status="rejected",
            chosen_action_rank=None,
            human_reason="rejected",
        )
    )
    assert s.approval_status == "rejected"


def test_request_bodies_validate() -> None:
    ApproveRequest(chosen_action_rank=1)
    RejectRequest(human_reason="bad idea")
    OverrideRequest(override_action="hold trucks", human_reason="visible plume")
