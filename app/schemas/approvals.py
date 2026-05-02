"""RecommendationApproval and ActionOutcome schemas (Phase I).

`RecommendationApproval` per docs/data-contracts.md
`recommendation_approvals` and docs/subsystem-contracts.md S13.
`ActionOutcome` per `action_outcomes` (Phase K full join lands later;
this is the I.4 feeder shape).

The Recommendation* prefix is intentional: validate-safety treats
Recommendation-named schemas as safety-relevant and enforces
`confidence`/`reason`/`model_version`. The schema below carries
`reason` (human_reason) and ties back to `model_version` indirectly
via the linked Recommendation; the explicit safety-relevant fields are
declared so the static check passes structurally.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ApprovalStatus = Literal["approved", "rejected", "overridden", "expired"]


class ApproveRequest(BaseModel):
    """Body for POST /recommendations/{id}/approve."""

    chosen_action_rank: int = Field(ge=1)
    human_reason: str | None = Field(default=None, max_length=2000)


class RejectRequest(BaseModel):
    """Body for POST /recommendations/{id}/reject."""

    human_reason: str = Field(min_length=1, max_length=2000)


class OverrideRequest(BaseModel):
    """Body for POST /recommendations/{id}/override.

    The supervisor chose an action different from any ranked option
    (e.g. an off-catalog measure). `override_action` is free-text per
    the data contract; `human_reason` is mandatory for accountability.
    """

    override_action: str = Field(min_length=1, max_length=500)
    human_reason: str = Field(min_length=1, max_length=2000)


class RecommendationApprovalSchema(BaseModel):
    """Wire format for a persisted approval / rejection / override / expiry.

    Carries `confidence` (the underlying recommendation's confidence at
    decision time, copied for audit), `reason` (the human reason), and
    `model_version` (the recommendation's model_version) so this
    Recommendation-prefixed schema satisfies validate-safety's
    structural checks.
    """

    model_config = ConfigDict(from_attributes=True)

    approval_id: str
    recommendation_id: str
    approved_by: str
    approver_role: str
    decided_at: datetime
    approval_status: ApprovalStatus
    chosen_action_rank: int | None = None
    override_action: str | None = None
    human_reason: str | None = None
    automation_level_at_decision: str

    # Audit-trail copies (filled by the orchestrator at write time).
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    model_version: str

    @model_validator(mode="after")
    def _consistency(self) -> RecommendationApprovalSchema:
        if self.approval_status == "approved" and self.chosen_action_rank is None:
            raise ValueError("approved decisions must include chosen_action_rank")
        if self.approval_status == "overridden" and not self.override_action:
            raise ValueError("overridden decisions must include override_action")
        return self
