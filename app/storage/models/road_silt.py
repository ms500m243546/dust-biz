"""HaulRoadSegmentSilt ORM (Phase L.7).

Per-segment periodic silt-content samples. Drives the `s` term in
the EPA AP-42 unpaved-haul-road emission factor:

    E (lb/VMT) = k * (s/12)^a * (W/3)^b

Sampling is typically quarterly to biannual; this is a sample log,
not a continuous reading, so it stays append-only with timestamp.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.storage.models.base import Base


class HaulRoadSegmentSilt(Base):
    __tablename__ = "haul_road_segment_silt"

    sample_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    segment_id: Mapped[str] = mapped_column(
        ForeignKey("haul_road_segments.segment_id"), nullable=False, index=True
    )
    sampled_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, index=True
    )
    silt_content_pct: Mapped[float] = mapped_column(Float, nullable=False)
    sampling_method: Mapped[str | None] = mapped_column(String, nullable=True)
    sampled_by: Mapped[str | None] = mapped_column(String, nullable=True)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
