"""Audit-log writer (Phase I, S15 partial).

Single seam used by every decision path that must be auditable per
safety-guardrails.md "Mandatory audit list". Domain code calls
`record(...)`; the writer flushes an `AuditLog` row through the
repository.

Phase I covers:
- recommendation issuance (back-fill from S12 path optional; not done
  retroactively to keep this step additive)
- approve / reject / override / expire decisions (S13)
- outcome capture (S14 feeder; I.4)

Future phases extend by adding new `action` strings; the table shape
stays stable.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.storage.models import AuditLog
from app.storage.repositories.audit import AuditLogRepository


def record(
    session: Session,
    *,
    actor: str,
    action: str,
    entity_type: str,
    entity_id: str,
    payload: dict[str, Any] | None = None,
    occurred_at: datetime | None = None,
) -> AuditLog:
    """Append one audit-log row. Returns the persisted row."""
    moment = (occurred_at or datetime.now(UTC)).replace(microsecond=0)
    if moment.tzinfo is not None:
        moment = moment.replace(tzinfo=None)
    row = AuditLog(
        occurred_at=moment,
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=dict(payload or {}),
    )
    return AuditLogRepository(session).add(row)


__all__ = ["record"]
