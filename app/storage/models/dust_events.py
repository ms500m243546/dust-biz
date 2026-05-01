"""DustEvent ORM (Phase F).

Per docs/data-contracts.md `dust_events`. Append-only audit table:
each detected dust event lands here with full lineage to the
predictions that flagged it. Events may also be entered manually
by operators (G12).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.storage.models.base import Base


class DustEvent(Base):
    __tablename__ = "dust_events"

    event_id: Mapped[str] = mapped_column(String, primary_key=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    affected_station: Mapped[str] = mapped_column(
        ForeignKey("sensors.sensor_id"), nullable=False, index=True
    )
    peak_pm10: Mapped[float] = mapped_column(Float, nullable=False)
    peak_pm25: Mapped[float] = mapped_column(Float, nullable=False)
    breach_occurred: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    event_source: Mapped[str] = mapped_column(String, nullable=False)
    linked_prediction_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
