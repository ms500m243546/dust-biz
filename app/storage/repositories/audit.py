"""AuditLog repository (Phase I).

Append-only by design: there is no `update` or `delete`. Reads are
filterable by entity for the dashboard's audit-trail view (J).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from app.storage.models import AuditLog
from app.storage.repositories.base import BaseRepository


class AuditLogRepository(BaseRepository):
    def add(self, row: AuditLog) -> AuditLog:
        self.session.add(row)
        self.session.flush()
        return row

    def get_recent(
        self,
        since: datetime,
        limit: int = 500,
        entity_type: str | None = None,
        entity_id: str | None = None,
    ) -> list[AuditLog]:
        stmt = (
            select(AuditLog)
            .where(AuditLog.occurred_at >= since)
            .order_by(AuditLog.occurred_at.desc())
            .limit(limit)
        )
        if entity_type is not None:
            stmt = stmt.where(AuditLog.entity_type == entity_type)
        if entity_id is not None:
            stmt = stmt.where(AuditLog.entity_id == entity_id)
        return list(self.session.execute(stmt).scalars())

    def for_entity(self, entity_type: str, entity_id: str) -> list[AuditLog]:
        stmt = (
            select(AuditLog)
            .where(AuditLog.entity_type == entity_type)
            .where(AuditLog.entity_id == entity_id)
            .order_by(AuditLog.occurred_at.asc())
        )
        return list(self.session.execute(stmt).scalars())
