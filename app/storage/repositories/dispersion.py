"""DispersionMatrix repository (Phase BA.5)."""

from __future__ import annotations

from sqlalchemy import select

from app.storage.models import DispersionMatrix
from app.storage.repositories.base import BaseRepository


class DispersionMatrixRepository(BaseRepository):
    def add(self, row: DispersionMatrix) -> DispersionMatrix:
        self.session.add(row)
        self.session.flush()
        return row

    def latest_for_mine(
        self, mine_id: str, *, model_version: str | None = None
    ) -> DispersionMatrix | None:
        stmt = (
            select(DispersionMatrix)
            .where(DispersionMatrix.mine_id == mine_id)
            .order_by(DispersionMatrix.created_at.desc())
            .limit(1)
        )
        if model_version is not None:
            stmt = stmt.where(DispersionMatrix.model_version == model_version)
        return self.session.execute(stmt).scalar_one_or_none()

    def all_for_mine(self, mine_id: str) -> list[DispersionMatrix]:
        stmt = (
            select(DispersionMatrix)
            .where(DispersionMatrix.mine_id == mine_id)
            .order_by(DispersionMatrix.created_at.desc())
        )
        return list(self.session.execute(stmt).scalars())
