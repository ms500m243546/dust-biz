"""EquipmentActivity repository."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from app.storage.models import EquipmentActivity
from app.storage.repositories.base import BaseRepository


class EquipmentActivityRepository(BaseRepository):
    def add(self, activity: EquipmentActivity) -> EquipmentActivity:
        self.session.add(activity)
        self.session.flush()
        return activity

    def add_many(self, activities: list[EquipmentActivity]) -> list[EquipmentActivity]:
        self.session.add_all(activities)
        self.session.flush()
        return activities

    def get_recent_for_equipment(
        self, equipment_id: str, since: datetime, limit: int = 1000
    ) -> list[EquipmentActivity]:
        stmt = (
            select(EquipmentActivity)
            .where(EquipmentActivity.equipment_id == equipment_id)
            .where(EquipmentActivity.timestamp >= since)
            .order_by(EquipmentActivity.timestamp.desc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars())

    def get_recent_for_zone(
        self, zone_id: str, since: datetime, limit: int = 1000
    ) -> list[EquipmentActivity]:
        stmt = (
            select(EquipmentActivity)
            .where(EquipmentActivity.zone_id == zone_id)
            .where(EquipmentActivity.timestamp >= since)
            .order_by(EquipmentActivity.timestamp.desc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars())
