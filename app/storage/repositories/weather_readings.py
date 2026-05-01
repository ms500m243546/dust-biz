"""WeatherReading repository."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from app.storage.models import WeatherReading
from app.storage.repositories.base import BaseRepository


class WeatherReadingRepository(BaseRepository):
    def add(self, reading: WeatherReading) -> WeatherReading:
        self.session.add(reading)
        self.session.flush()
        return reading

    def add_many(self, readings: list[WeatherReading]) -> list[WeatherReading]:
        self.session.add_all(readings)
        self.session.flush()
        return readings

    def get_recent(
        self, source: str, since: datetime, limit: int = 1000
    ) -> list[WeatherReading]:
        stmt = (
            select(WeatherReading)
            .where(WeatherReading.source == source)
            .where(WeatherReading.timestamp >= since)
            .order_by(WeatherReading.timestamp.desc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars())

    def get_recent_for_zone(
        self, zone_id: str, since: datetime, limit: int = 1000
    ) -> list[WeatherReading]:
        stmt = (
            select(WeatherReading)
            .where(WeatherReading.zone_id == zone_id)
            .where(WeatherReading.timestamp >= since)
            .order_by(WeatherReading.timestamp.desc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars())
