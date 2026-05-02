"""PopulatedPlace ORM (Phase L.1).

Per docs/data-source-registry.md. Receptor metadata loaded from INE
populated-place geometries + SEA RCA receptor lists. Mutable: a
mine's receptor list can be updated when an RCA amendment changes
the recognised set of community stations / sensitive infrastructure.
"""

from __future__ import annotations

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.storage.models.base import Base


class PopulatedPlace(Base):
    __tablename__ = "populated_places"

    place_id: Mapped[str] = mapped_column(String, primary_key=True)
    mine_id: Mapped[str] = mapped_column(
        ForeignKey("mines.mine_id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False, index=True)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    population: Mapped[int | None] = mapped_column(Integer, nullable=True)
    distance_to_mine_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    bearing_from_mine_deg: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String, nullable=False, default="ine")
    source_url: Mapped[str | None] = mapped_column(String, nullable=True)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
