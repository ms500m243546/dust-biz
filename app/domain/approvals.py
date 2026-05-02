"""Recommendation approval orchestrator (S13, Phase I).

Enforces:
- Guardrail 1: medium/high `risk_class` actions require human approval; the
  approval endpoint is the only path that records that approval.
- Guardrail 13: high `risk_class` actions never auto-execute regardless of
  automation level (recorded as `automation_level_at_decision`).
- Guardrail 8: every decision is persisted, even rejections and expiries.
- Guardrail 9: overrides capture who, when, what they chose instead, and why.
- Lazy expiry: when an approval is requested past `approval_expiry_minutes`
  from the recommendation's issued_at, the orchestrator records an
  `expired` row instead of accepting the decision. A manual sweep
  endpoint covers recommendations that were never decided on.

Layer rule: this module imports schemas, storage, and audit, but never
the API layer.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import record as audit_record
from app.domain.site_config_resolver import require_resolved
from app.schemas.approvals import (
    ApprovalStatus,
    RecommendationApprovalSchema,
)
from app.storage.models import (
    Mine,
    Recommendation,
    RecommendationApproval,
    SiteConfiguration,
    Zone,
)
from app.storage.repositories.approvals import RecommendationApprovalRepository
from app.storage.repositories.recommendations import RecommendationRepository

DEFAULT_APPROVAL_EXPIRY_MINUTES = 15


class RecommendationNotFoundError(Exception):
    pass


class AlreadyDecidedError(Exception):
    pass


class ExpiredRecommendationError(Exception):
    pass


class InvalidActionRankError(Exception):
    pass


class HighRiskAutoExecutionError(Exception):
    """G13: a high-risk action cannot be approved by a path that
    bypasses human accountability. Defensive raise; in practice this
    fires only when the caller passes an action_rank pointing at a
    high-risk action whose `requires_human_approval` flag was set to
    False, which would itself be a contract violation upstream.
    """


def approve_recommendation(
    *,
    session: Session,
    recommendation_id: str,
    chosen_action_rank: int,
    human_reason: str | None,
    actor_username: str,
    actor_role: str,
    now: datetime | None = None,
) -> RecommendationApprovalSchema:
    rec, expiry_minutes = _load_or_raise(session, recommendation_id)
    moment = _moment(now)
    _guard_already_decided(session, recommendation_id)
    if _is_expired(rec, moment, expiry_minutes):
        return _record_expired(session, rec, moment, expiry_minutes)

    actions = list(rec.recommended_actions or [])
    chosen = _find_action(actions, chosen_action_rank)
    if chosen is None:
        raise InvalidActionRankError(
            f"chosen_action_rank {chosen_action_rank} not present in recommendation"
        )
    if chosen.get("risk_class") == "high":
        raise HighRiskAutoExecutionError(
            "high risk_class actions cannot be approved through this path; "
            "use override with explicit human_reason"
        )
    return _persist_decision(
        session=session,
        rec=rec,
        actor_username=actor_username,
        actor_role=actor_role,
        moment=moment,
        approval_status="approved",
        chosen_action_rank=chosen_action_rank,
        override_action=None,
        human_reason=human_reason,
    )


def reject_recommendation(
    *,
    session: Session,
    recommendation_id: str,
    human_reason: str,
    actor_username: str,
    actor_role: str,
    now: datetime | None = None,
) -> RecommendationApprovalSchema:
    rec, expiry_minutes = _load_or_raise(session, recommendation_id)
    moment = _moment(now)
    _guard_already_decided(session, recommendation_id)
    if _is_expired(rec, moment, expiry_minutes):
        return _record_expired(session, rec, moment, expiry_minutes)
    return _persist_decision(
        session=session,
        rec=rec,
        actor_username=actor_username,
        actor_role=actor_role,
        moment=moment,
        approval_status="rejected",
        chosen_action_rank=None,
        override_action=None,
        human_reason=human_reason,
    )


def override_recommendation(
    *,
    session: Session,
    recommendation_id: str,
    override_action: str,
    human_reason: str,
    actor_username: str,
    actor_role: str,
    now: datetime | None = None,
) -> RecommendationApprovalSchema:
    rec, expiry_minutes = _load_or_raise(session, recommendation_id)
    moment = _moment(now)
    _guard_already_decided(session, recommendation_id)
    if _is_expired(rec, moment, expiry_minutes):
        return _record_expired(session, rec, moment, expiry_minutes)
    return _persist_decision(
        session=session,
        rec=rec,
        actor_username=actor_username,
        actor_role=actor_role,
        moment=moment,
        approval_status="overridden",
        chosen_action_rank=None,
        override_action=override_action,
        human_reason=human_reason,
    )


def sweep_expired(
    *,
    session: Session,
    now: datetime | None = None,
    limit: int = 200,
) -> list[RecommendationApprovalSchema]:
    """Find recommendations past their expiry window and record `expired` rows.

    Returns the list of newly expired approvals. Does nothing if a
    recommendation already has any approval row.
    """
    moment = _moment(now)
    rec_repo = RecommendationRepository(session)
    appr_repo = RecommendationApprovalRepository(session)

    cutoff = moment - timedelta(minutes=DEFAULT_APPROVAL_EXPIRY_MINUTES * 4)
    results: list[RecommendationApprovalSchema] = []
    for rec in rec_repo.get_recent(since=cutoff, limit=limit):
        if appr_repo.latest_for_recommendation(rec.recommendation_id) is not None:
            continue
        expiry_minutes = _expiry_minutes_for(session, rec)
        if not _is_expired(rec, moment, expiry_minutes):
            continue
        results.append(_record_expired(session, rec, moment, expiry_minutes))
    return results


def latest_for_recommendation(
    *, session: Session, recommendation_id: str
) -> RecommendationApprovalSchema | None:
    row = RecommendationApprovalRepository(session).latest_for_recommendation(
        recommendation_id
    )
    if row is None:
        return None
    rec = RecommendationRepository(session).get(recommendation_id)
    if rec is None:
        return None
    return _hydrate(row, rec)


def _moment(now: datetime | None) -> datetime:
    moment = (now or datetime.now(UTC)).replace(microsecond=0)
    if moment.tzinfo is not None:
        moment = moment.replace(tzinfo=None)
    return moment


def _load_or_raise(
    session: Session, recommendation_id: str
) -> tuple[Recommendation, int]:
    rec = RecommendationRepository(session).get(recommendation_id)
    if rec is None:
        raise RecommendationNotFoundError(
            f"recommendation not found: {recommendation_id}"
        )
    return rec, _expiry_minutes_for(session, rec)


def _expiry_minutes_for(session: Session, rec: Recommendation) -> int:
    zone = session.get(Zone, rec.target_zone_id)
    if zone is None:
        return DEFAULT_APPROVAL_EXPIRY_MINUTES
    mine = session.get(Mine, zone.mine_id)
    site_cfgs = list(
        session.execute(
            select(SiteConfiguration).where(SiteConfiguration.mine_id == zone.mine_id)
        ).scalars()
    )
    if not site_cfgs and mine is None:
        return DEFAULT_APPROVAL_EXPIRY_MINUTES
    try:
        cfg = require_resolved(
            mine_id=zone.mine_id,
            site_config=site_cfgs[0] if site_cfgs else None,
            mine=mine,
        )
    except Exception:
        return DEFAULT_APPROVAL_EXPIRY_MINUTES
    return getattr(cfg, "approval_expiry_minutes", DEFAULT_APPROVAL_EXPIRY_MINUTES)


def _guard_already_decided(session: Session, recommendation_id: str) -> None:
    existing = RecommendationApprovalRepository(session).latest_for_recommendation(
        recommendation_id
    )
    if existing is not None:
        raise AlreadyDecidedError(
            f"recommendation {recommendation_id} already has decision "
            f"'{existing.approval_status}' at {existing.decided_at.isoformat()}"
        )


def _is_expired(
    rec: Recommendation, moment: datetime, expiry_minutes: int
) -> bool:
    issued = rec.issued_at
    if issued.tzinfo is not None:
        issued = issued.replace(tzinfo=None)
    return moment >= issued + timedelta(minutes=expiry_minutes)


def _find_action(actions: list[dict[str, object]], rank: int) -> dict[str, object] | None:
    for a in actions:
        if a.get("rank") == rank:
            return a
    return None


def _persist_decision(
    *,
    session: Session,
    rec: Recommendation,
    actor_username: str,
    actor_role: str,
    moment: datetime,
    approval_status: ApprovalStatus,
    chosen_action_rank: int | None,
    override_action: str | None,
    human_reason: str | None,
) -> RecommendationApprovalSchema:
    repo = RecommendationApprovalRepository(session)
    approval_id = repo.next_approval_id(moment)
    row = RecommendationApproval(
        approval_id=approval_id,
        recommendation_id=rec.recommendation_id,
        approved_by=actor_username,
        approver_role=actor_role,
        decided_at=moment,
        approval_status=approval_status,
        chosen_action_rank=chosen_action_rank,
        override_action=override_action,
        human_reason=human_reason,
        automation_level_at_decision=rec.automation_level,
    )
    repo.add(row)
    audit_record(
        session,
        actor=actor_username,
        action=f"{approval_status}_recommendation",
        entity_type="recommendation",
        entity_id=rec.recommendation_id,
        payload={
            "approval_id": approval_id,
            "approver_role": actor_role,
            "chosen_action_rank": chosen_action_rank,
            "override_action": override_action,
            "human_reason": human_reason,
            "automation_level_at_decision": rec.automation_level,
        },
        occurred_at=moment,
    )
    return _hydrate(row, rec)


def _record_expired(
    session: Session,
    rec: Recommendation,
    moment: datetime,
    expiry_minutes: int,
) -> RecommendationApprovalSchema:
    repo = RecommendationApprovalRepository(session)
    approval_id = repo.next_approval_id(moment)
    row = RecommendationApproval(
        approval_id=approval_id,
        recommendation_id=rec.recommendation_id,
        approved_by="system",
        approver_role="system",
        decided_at=moment,
        approval_status="expired",
        chosen_action_rank=None,
        override_action=None,
        human_reason=(
            f"no decision recorded within {expiry_minutes} minutes of issuance"
        ),
        automation_level_at_decision=rec.automation_level,
    )
    repo.add(row)
    audit_record(
        session,
        actor="system",
        action="expired_recommendation",
        entity_type="recommendation",
        entity_id=rec.recommendation_id,
        payload={
            "approval_id": approval_id,
            "expiry_minutes": expiry_minutes,
            "automation_level_at_decision": rec.automation_level,
        },
        occurred_at=moment,
    )
    return _hydrate(row, rec)


def _hydrate(
    row: RecommendationApproval, rec: Recommendation
) -> RecommendationApprovalSchema:
    return RecommendationApprovalSchema(
        approval_id=row.approval_id,
        recommendation_id=row.recommendation_id,
        approved_by=row.approved_by,
        approver_role=row.approver_role,
        decided_at=row.decided_at,
        approval_status=row.approval_status,  # type: ignore[arg-type]
        chosen_action_rank=row.chosen_action_rank,
        override_action=row.override_action,
        human_reason=row.human_reason,
        automation_level_at_decision=row.automation_level_at_decision,
        confidence=rec.confidence,
        reason=rec.reason,
        model_version=rec.model_version,
    )


__all__ = [
    "AlreadyDecidedError",
    "DEFAULT_APPROVAL_EXPIRY_MINUTES",
    "ExpiredRecommendationError",
    "HighRiskAutoExecutionError",
    "InvalidActionRankError",
    "RecommendationNotFoundError",
    "approve_recommendation",
    "latest_for_recommendation",
    "override_recommendation",
    "reject_recommendation",
    "sweep_expired",
]
