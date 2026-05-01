"""Equipment + activity schemas.

Per docs/data-contracts.md `equipment` and `equipment_activity`.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

EquipmentType = Literal[
    "truck",
    "shovel",
    "crusher",
    "drill",
    "dozer",
    "grader",
    "water_truck",
    "other",
]
ActivityType = Literal[
    "idle",
    "loading",
    "hauling",
    "dumping",
    "drilling",
    "crushing",
    "watering",
    "grading",
    "maintenance",
    "other",
]


class EquipmentSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    equipment_id: str
    mine_id: str
    equipment_type: EquipmentType
    nominal_capacity_t: float | None = Field(default=None, ge=0.0)


class RawEquipmentActivitySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    equipment_id: str
    timestamp: datetime
    activity_type: ActivityType
    zone_id: str | None = None
    speed_kmh: float | None = Field(default=None, ge=0.0)
    tonnage: float | None = Field(default=None, ge=0.0)
    raw_payload: dict[str, Any] = Field(default_factory=dict)
