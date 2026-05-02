"""StationThresholdOverride repository (Phase L.6)."""

from __future__ import annotations

from sqlalchemy import select

from app.storage.models import StationThresholdOverride
from app.storage.repositories.base import BaseRepository


class StationThresholdOverrideRepository(BaseRepository):
    def add(self, row: StationThresholdOverride) -> StationThresholdOverride:
        self.session.add(row)
        self.session.flush()
        return row

    def get_for_sensor(self, sensor_id: str) -> StationThresholdOverride | None:
        stmt = (
            select(StationThresholdOverride)
            .where(StationThresholdOverride.sensor_id == sensor_id)
            .order_by(StationThresholdOverride.updated_at.desc())
            .limit(1)
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def get_for_site(self, site_id: str) -> list[StationThresholdOverride]:
        stmt = select(StationThresholdOverride).where(
            StationThresholdOverride.site_id == site_id
        )
        return list(self.session.execute(stmt).scalars())

    def upsert_for_sensor(
        self, row: StationThresholdOverride
    ) -> StationThresholdOverride:
        existing = self.get_for_sensor(row.sensor_id)
        if existing is None:
            return self.add(row)
        for col in (
            "site_id",
            "pm10_warning_ugm3",
            "pm10_breach_ugm3",
            "pm25_warning_ugm3",
            "pm25_breach_ugm3",
            "rca_reference",
            "source_url",
            "notes",
        ):
            setattr(existing, col, getattr(row, col))
        self.session.flush()
        return existing
