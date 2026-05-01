"""MineStateSnapshot repository.

Append-only: snapshots are immutable historical records. Reads return
the most recent snapshot per zone (or per mine).
"""

from __future__ import annotations

from sqlalchemy import select

from app.storage.models import MineStateSnapshot, Zone
from app.storage.repositories.base import BaseRepository


class MineStateSnapshotRepository(BaseRepository):
    def add(self, snapshot: MineStateSnapshot) -> MineStateSnapshot:
        self.session.add(snapshot)
        self.session.flush()
        return snapshot

    def add_many(self, snapshots: list[MineStateSnapshot]) -> list[MineStateSnapshot]:
        self.session.add_all(snapshots)
        self.session.flush()
        return snapshots

    def latest_for_zone(self, zone_id: str) -> MineStateSnapshot | None:
        stmt = (
            select(MineStateSnapshot)
            .where(MineStateSnapshot.zone_id == zone_id)
            .order_by(MineStateSnapshot.timestamp.desc())
            .limit(1)
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def latest_for_mine(self, mine_id: str) -> list[MineStateSnapshot]:
        # Latest snapshot per zone for a given mine. Two-step:
        # (1) find the mine's zones, (2) take the most recent row per
        # zone. Postgres swap (R8) will replace this with a window
        # function; SQLite doesn't pay enough at MVP scale to bother.
        zone_ids = list(
            self.session.execute(select(Zone.zone_id).where(Zone.mine_id == mine_id)).scalars()
        )
        out: list[MineStateSnapshot] = []
        for zid in zone_ids:
            latest = self.latest_for_zone(zid)
            if latest is not None:
                out.append(latest)
        return out
