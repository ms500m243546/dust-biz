"""DustEvent ORM (Phase F).

Per docs/data-contracts.md `dust_events`. Append-only audit table:
each detected dust event lands here with full lineage to the
predictions that flagged it. Events may also be entered manually
by operators (G12).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.storage.models.base import Base


def _default_labeled_at_from_detected(context: Any) -> datetime:
    detected_at: datetime = context.get_current_parameters()["detected_at"]
    return detected_at


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
    # M.2: anti-hindsight rule 3. `labeled_at` is when the breach label
    # was assigned. A label is legal as a training feature for
    # prediction `p` only if `labeled_at <= p.issued_at`. Default =
    # `detected_at` (context-aware); callers may override for
    # post-event analysis labels which carry a later `labeled_at`.
    labeled_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=_default_labeled_at_from_detected,
        index=True,
    )
