"""Mine + Zone schemas.

Static spatial entities. Per docs/data-contracts.md.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ZoneType = Literal[
    "pit",
    "haul_road",
    "stockpile",
    "dump",
    "crusher",
    "loading_area",
    "boundary",
]
OperationalImportance = Literal["low", "medium", "high", "critical"]
DustGenerationBaseline = Literal["low", "medium", "high"]
AutomationLevel = Literal["L0", "L1", "L2", "L3", "L4"]


class MineSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    mine_id: str
    name: str
    default_automation_level: AutomationLevel = "L1"


class ZoneSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    zone_id: str
    mine_id: str
    zone_type: ZoneType
    operational_importance: OperationalImportance
    dust_generation_baseline: DustGenerationBaseline
    allowed_interventions: tuple[str, ...] = Field(default_factory=tuple)
    requires_approval_for: tuple[str, ...] = Field(default_factory=tuple)


class HaulRoadSegmentSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    segment_id: str
    mine_id: str
    from_node: str
    to_node: str
    length_m: float
    surface_type: str
