"""InterventionSimulation repository.

Append-only writes. IDs follow `SIM-YYYYMMDD-NNNN` resetting per UTC
day, matching the patterns used by predictions / events / attributions.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import func, select

from app.storage.models import InterventionSimulation
from app.storage.repositories.base import BaseRepository


class InterventionSimulationRepository(BaseRepository):
    def add(self, sim: InterventionSimulation) -> InterventionSimulation:
        self.session.add(sim)
        self.session.flush()
        return sim

    def get(self, simulation_id: str) -> InterventionSimulation | None:
        return self.session.get(InterventionSimulation, simulation_id)

    def get_recent(
        self,
        since: datetime,
        limit: int = 200,
        target_zone_id: str | None = None,
    ) -> list[InterventionSimulation]:
        stmt = (
            select(InterventionSimulation)
            .where(InterventionSimulation.requested_at >= since)
            .order_by(InterventionSimulation.requested_at.desc())
            .limit(limit)
        )
        if target_zone_id is not None:
            stmt = stmt.where(InterventionSimulation.target_zone_id == target_zone_id)
        return list(self.session.execute(stmt).scalars())

    def next_simulation_id(self, on_date: date) -> str:
        prefix = f"SIM-{on_date.strftime('%Y%m%d')}-"
        stmt = select(func.count()).where(
            InterventionSimulation.simulation_id.like(prefix + "%")
        )
        n = self.session.execute(stmt).scalar_one() or 0
        return f"{prefix}{n + 1:04d}"
