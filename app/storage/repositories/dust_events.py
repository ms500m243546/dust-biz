"""DustEvent repository.

Append + read access. Event IDs follow `EVT-YYYYMMDD-NNN`
(data-contracts.md line 150) with the sequence resetting per UTC
day; the orchestrator generates them via `next_event_id`.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import func, select

from app.storage.models import DustEvent
from app.storage.repositories.base import BaseRepository


class DustEventRepository(BaseRepository):
    def add(self, event: DustEvent) -> DustEvent:
        self.session.add(event)
        self.session.flush()
        return event

    def get(self, event_id: str) -> DustEvent | None:
        return self.session.get(DustEvent, event_id)

    def get_recent(
        self, since: datetime, limit: int = 200, station: str | None = None
    ) -> list[DustEvent]:
        stmt = (
            select(DustEvent)
            .where(DustEvent.detected_at >= since)
            .order_by(DustEvent.detected_at.desc())
            .limit(limit)
        )
        if station is not None:
            stmt = stmt.where(DustEvent.affected_station == station)
        return list(self.session.execute(stmt).scalars())

    def next_event_id(self, on_date: date) -> str:
        """`EVT-YYYYMMDD-NNN` per data-contracts.md line 150."""
        prefix = f"EVT-{on_date.strftime('%Y%m%d')}-"
        stmt = select(func.count()).where(DustEvent.event_id.like(prefix + "%"))
        n = self.session.execute(stmt).scalar_one() or 0
        return f"{prefix}{n + 1:03d}"
