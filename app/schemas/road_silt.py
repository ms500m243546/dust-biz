"""HaulRoadSegmentSilt schema (Phase L.7).

Per-segment silt-content samples for EPA AP-42 unpaved-road emission
modelling. See docs/data-source-registry.md for sampling cadence
guidance.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class HaulRoadSegmentSiltSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sample_id: int | None = None
    segment_id: str
    sampled_at: datetime
    silt_content_pct: float = Field(ge=0.0, le=100.0)
    sampling_method: str | None = None
    sampled_by: str | None = None
    notes: str | None = None


__all__ = ["HaulRoadSegmentSiltSchema"]
