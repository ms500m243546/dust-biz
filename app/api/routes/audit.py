"""Audit endpoints (Phase J deslop).

GET /api/v1/audit  - recent audit-log entries from the canonical
                     `audit_logs` table written by S13 + S14 + auth +
                     forecasting. Auth-gated for any signed-in user;
                     the table is append-only by design.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies.auth import current_user
from app.api.deps import get_session
from app.schemas.audit import AuditLogSchema
from app.storage.models import User
from app.storage.repositories.audit import AuditLogRepository

router = APIRouter(prefix="/audit", tags=["audit"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("", response_model=list[AuditLogSchema])
def list_recent(
    session: SessionDep,
    _user: Annotated[User, Depends(current_user)],
    since_minutes: Annotated[int, Query(ge=1, le=24 * 60 * 30)] = 24 * 60,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    entity_type: Annotated[str | None, Query()] = None,
    entity_id: Annotated[str | None, Query()] = None,
) -> list[AuditLogSchema]:
    since = (datetime.now(UTC) - timedelta(minutes=since_minutes)).replace(tzinfo=None)
    rows = AuditLogRepository(session).get_recent(
        since=since,
        limit=limit,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    return [AuditLogSchema.model_validate(r) for r in rows]
