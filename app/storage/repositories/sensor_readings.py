"""SensorReading repository.

Append + read access for raw sensor readings. Raw readings are
immutable once written (docs/data-contracts.md "Separation rules").
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select

from app.storage.models import SensorReading
from app.storage.repositories.base import BaseRepository


class SensorReadingRepository(BaseRepository):
    def add(
        self,
        sensor_id: str,
        timestamp: datetime,
        raw_value: dict[str, Any],
        source_quality_hint: float | None = None,
    ) -> SensorReading:
        reading = SensorReading(
            sensor_id=sensor_id,
            timestamp=timestamp,
            raw_value=raw_value,
            source_quality_hint=source_quality_hint,
        )
        self.session.add(reading)
        self.session.flush()
        return reading

    def add_many(self, readings: list[SensorReading]) -> list[SensorReading]:
        self.session.add_all(readings)
        self.session.flush()
        return readings

    def get_recent(
        self, sensor_id: str, since: datetime, limit: int = 1000
    ) -> list[SensorReading]:
        stmt = (
            select(SensorReading)
            .where(SensorReading.sensor_id == sensor_id)
            .where(SensorReading.timestamp >= since)
            .order_by(SensorReading.timestamp.desc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars())

    def get_for_sensor(self, sensor_id: str, limit: int = 100) -> list[SensorReading]:
        stmt = (
            select(SensorReading)
            .where(SensorReading.sensor_id == sensor_id)
            .order_by(SensorReading.timestamp.desc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars())
