"""Zone repository.

Zones describe static spatial entities (pits, haul roads, stockpiles,
boundaries, etc.). Operators register them once per mine and rarely
mutate them; the repository supports `upsert` for occasional
re-registration without forcing callers to branch on insert/update.
"""

from __future__ import annotations

from sqlalchemy import select

from app.storage.models import Zone
from app.storage.repositories.base import BaseRepository


class ZoneRepository(BaseRepository):
    def get(self, zone_id: str) -> Zone | None:
        return self.session.get(Zone, zone_id)

    def get_for_mine(self, mine_id: str) -> list[Zone]:
        stmt = select(Zone).where(Zone.mine_id == mine_id)
        return list(self.session.execute(stmt).scalars())

    def upsert(
        self,
        zone_id: str,
        mine_id: str,
        zone_type: str,
        operational_importance: str,
        dust_generation_baseline: str,
        allowed_interventions: list[str] | None = None,
        requires_approval_for: list[str] | None = None,
    ) -> Zone:
        existing = self.session.get(Zone, zone_id)
        if existing is None:
            zone = Zone(
                zone_id=zone_id,
                mine_id=mine_id,
                zone_type=zone_type,
                operational_importance=operational_importance,
                dust_generation_baseline=dust_generation_baseline,
                allowed_interventions=allowed_interventions or [],
                requires_approval_for=requires_approval_for or [],
            )
            self.session.add(zone)
        else:
            existing.mine_id = mine_id
            existing.zone_type = zone_type
            existing.operational_importance = operational_importance
            existing.dust_generation_baseline = dust_generation_baseline
            existing.allowed_interventions = allowed_interventions or []
            existing.requires_approval_for = requires_approval_for or []
            zone = existing
        self.session.flush()
        return zone
