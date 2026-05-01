"""DustEvent schemas (Phase F).

Per docs/data-contracts.md `dust_events` and
docs/subsystem-contracts.md S7 (input). A dust event is a moment
worth attributing - it can come from a model alert (forecast
breach probability crossed threshold), a manual entry by an
operator (G12), or a threshold trigger (raw PM10 above the
configurable site threshold). Events feed the attribution engine
and the outcome-capture loop in K.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EventSource = Literal["model_alert", "manual_entry", "threshold_trigger"]


class DustEventCreate(BaseModel):
    """Request body for `POST /api/v1/dust-events`.

    `event_source` defaults to `manual_entry`; the threshold-trigger
    endpoint sets it to `threshold_trigger` server-side.
    """

    detected_at: datetime
    affected_station: str
    peak_pm10: float = Field(ge=0.0)
    peak_pm25: float = Field(ge=0.0)
    breach_occurred: bool = False
    event_source: EventSource = "manual_entry"
    linked_prediction_ids: list[str] = Field(default_factory=list)
    notes: str | None = None


class DustEventSchema(BaseModel):
    """Wire format for an issued / persisted dust event."""

    model_config = ConfigDict(from_attributes=True)

    event_id: str
    detected_at: datetime
    affected_station: str
    peak_pm10: float
    peak_pm25: float
    breach_occurred: bool
    event_source: EventSource
    linked_prediction_ids: list[str] = Field(default_factory=list)
    notes: str | None = None
