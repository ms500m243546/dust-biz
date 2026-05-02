"""SiteConfiguration repository.

Read + upsert. Site configs are mutable (operators tune thresholds and
weights at runtime), so this repository supports `upsert` rather than
the append-only pattern used by readings repos.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.storage.models import SiteConfiguration
from app.storage.repositories.base import BaseRepository


class SiteConfigRepository(BaseRepository):
    def get(self, site_id: str) -> SiteConfiguration | None:
        return self.session.get(SiteConfiguration, site_id)

    def get_for_mine(self, mine_id: str) -> list[SiteConfiguration]:
        stmt = select(SiteConfiguration).where(SiteConfiguration.mine_id == mine_id)
        return list(self.session.execute(stmt).scalars())

    def upsert(
        self,
        site_id: str,
        mine_id: str,
        automation_level: str,
        pm10_thresholds: dict[str, float],
        pm25_thresholds: dict[str, float],
        extreme_breach_threshold: float,
        low_confidence_threshold: float,
        optimization_weights: dict[str, float],
        intervention_constraints: dict[str, Any] | None = None,
        updated_by: str | None = None,
        approval_expiry_minutes: int = 15,
    ) -> SiteConfiguration:
        existing = self.session.get(SiteConfiguration, site_id)
        if existing is None:
            cfg = SiteConfiguration(
                site_id=site_id,
                mine_id=mine_id,
                automation_level=automation_level,
                pm10_thresholds=pm10_thresholds,
                pm25_thresholds=pm25_thresholds,
                extreme_breach_threshold=extreme_breach_threshold,
                low_confidence_threshold=low_confidence_threshold,
                optimization_weights=optimization_weights,
                intervention_constraints=intervention_constraints or {},
                updated_by=updated_by,
                approval_expiry_minutes=approval_expiry_minutes,
            )
            self.session.add(cfg)
        else:
            existing.mine_id = mine_id
            existing.automation_level = automation_level
            existing.pm10_thresholds = pm10_thresholds
            existing.pm25_thresholds = pm25_thresholds
            existing.extreme_breach_threshold = extreme_breach_threshold
            existing.low_confidence_threshold = low_confidence_threshold
            existing.optimization_weights = optimization_weights
            existing.intervention_constraints = intervention_constraints or {}
            existing.updated_by = updated_by
            existing.approval_expiry_minutes = approval_expiry_minutes
            cfg = existing
        self.session.flush()
        return cfg
