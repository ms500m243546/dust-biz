"""FeatureRecord repository.

Append-only writes. Reads return latest-per-zone or a windowed
history. Forecasting (S6) reads via `latest_for_zone`; offline
training (Phase K) will use windowed history.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from app.storage.models import FeatureRecord
from app.storage.repositories.base import BaseRepository


class FeatureRepository(BaseRepository):
    def add(self, record: FeatureRecord) -> FeatureRecord:
        self.session.add(record)
        self.session.flush()
        return record

    def add_many(self, records: list[FeatureRecord]) -> list[FeatureRecord]:
        self.session.add_all(records)
        self.session.flush()
        return records

    def latest_for_zone(self, zone_id: str) -> FeatureRecord | None:
        stmt = (
            select(FeatureRecord)
            .where(FeatureRecord.zone_id == zone_id)
            .order_by(FeatureRecord.timestamp.desc())
            .limit(1)
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def get_recent(
        self, zone_id: str, since: datetime, limit: int = 1000
    ) -> list[FeatureRecord]:
        stmt = (
            select(FeatureRecord)
            .where(FeatureRecord.zone_id == zone_id)
            .where(FeatureRecord.timestamp >= since)
            .order_by(FeatureRecord.timestamp.desc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars())
