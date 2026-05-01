"""MineState schemas.

Wire format per docs/subsystem-contracts.md S4. The S4 failure mode is
"if a contributing stream is stale, the affected fields are marked
`stale` rather than fabricated" - this is implemented by the
`staleness_flags` array, populated by the domain engine.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

DustGenerationPotential = Literal["low", "medium", "high", "unknown"]
WindExposure = Literal["low", "medium", "high", "unknown"]
ZoneActivity = Literal[
    "idle",
    "loading",
    "hauling",
    "dumping",
    "drilling",
    "crushing",
    "watering",
    "grading",
    "maintenance",
    "mixed",
    "unknown",
]


class MineStateZoneSchema(BaseModel):
    """Per-zone state snapshot.

    Matches the wire format at subsystem-contracts.md S4 plus
    `staleness_flags` for the documented failure mode.
    """

    model_config = ConfigDict(from_attributes=True)

    timestamp: datetime
    zone_id: str
    activity: ZoneActivity
    equipment_active: list[str] = Field(default_factory=list)
    production_rate_tph: float | None = None
    dust_generation_potential: DustGenerationPotential
    wind_exposure: WindExposure
    downwind_assets: list[str] = Field(default_factory=list)
    operational_importance: str
    staleness_flags: list[str] = Field(default_factory=list)

    @field_validator("equipment_active", "downwind_assets", "staleness_flags", mode="before")
    @classmethod
    def _coerce_none(cls, v: Any) -> Any:
        # SQLAlchemy `default=list` only fires on flush; unflushed reads
        # may expose None for the JSON columns.
        return [] if v is None else v


class MineStateSchema(BaseModel):
    """Aggregate mine state across all zones for a mine.

    Top-level wrapper returned by `GET /api/v1/mine-state/current`.
    """

    mine_id: str
    computed_at: datetime
    window_minutes: int
    zones: list[MineStateZoneSchema] = Field(default_factory=list)
