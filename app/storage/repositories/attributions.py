"""SourceAttribution repository.

Append-only writes. Reads return latest-per-event or windowed
history. IDs follow `ATTR-YYYYMMDD-NNN` resetting per UTC day.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import func, select

from app.storage.models import SourceAttribution
from app.storage.repositories.base import BaseRepository


class SourceAttributionRepository(BaseRepository):
    def add(self, attribution: SourceAttribution) -> SourceAttribution:
        self.session.add(attribution)
        self.session.flush()
        return attribution

    def latest_for_event(self, dust_event_id: str) -> SourceAttribution | None:
        stmt = (
            select(SourceAttribution)
            .where(SourceAttribution.dust_event_id == dust_event_id)
            .order_by(SourceAttribution.issued_at.desc())
            .limit(1)
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def history_for_event(self, dust_event_id: str) -> list[SourceAttribution]:
        stmt = (
            select(SourceAttribution)
            .where(SourceAttribution.dust_event_id == dust_event_id)
            .order_by(SourceAttribution.issued_at.desc())
        )
        return list(self.session.execute(stmt).scalars())

    def get_recent(self, since: datetime, limit: int = 200) -> list[SourceAttribution]:
        stmt = (
            select(SourceAttribution)
            .where(SourceAttribution.issued_at >= since)
            .order_by(SourceAttribution.issued_at.desc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars())

    def next_attribution_id(self, on_date: date) -> str:
        prefix = f"ATTR-{on_date.strftime('%Y%m%d')}-"
        stmt = select(func.count()).where(SourceAttribution.attribution_id.like(prefix + "%"))
        n = self.session.execute(stmt).scalar_one() or 0
        return f"{prefix}{n + 1:03d}"
