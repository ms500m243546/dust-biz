"""Shift-progress schema (Phase AA).

Captures where a mine sits within its current production shift so the
optimizer can scale production-cost weights against the actual slack
available — instead of treating every "200 tonnes delayed" the same
whether the shift is hours ahead of plan or behind it.

`source` is "live" when computed from real EquipmentActivity rows in
the shift window; "synthetic" when computed from operator-set
overrides in `SiteConfiguration.cost_curves`. The deferred-mode
fallback is the same pattern AP-42 / cycle-time cost models use until
real telematics arrives.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ShiftProgressSource = Literal["synthetic", "live"]


class ShiftProgressSchema(BaseModel):
    """Pure-data summary of where this mine is in its current shift."""

    model_config = ConfigDict(from_attributes=True)

    mine_id: str
    shift_start: datetime
    now: datetime
    hours_elapsed: float = Field(ge=0.0)
    hours_remaining: float = Field(ge=0.0)
    target_tonnes_per_hour: float = Field(gt=0.0)
    shift_target_tonnes: float = Field(gt=0.0)
    tonnes_done: float = Field(ge=0.0)
    expected_done: float = Field(ge=0.0)
    # slack_ratio = tonnes_done / max(expected_done, 1.0). >1 means
    # ahead of plan; <1 means behind. The ranker uses 1/slack_ratio as
    # the multiplier on `w_production`, clamped so noise can't swing
    # the recommendation wildly.
    slack_ratio: float = Field(ge=0.0)
    source: ShiftProgressSource = "synthetic"
