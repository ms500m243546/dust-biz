from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.equipment import EquipmentSchema, RawEquipmentActivitySchema


def test_equipment_basic() -> None:
    e = EquipmentSchema(
        equipment_id="Truck_17", mine_id="m1", equipment_type="truck", nominal_capacity_t=240.0
    )
    assert e.equipment_type == "truck"


def test_equipment_invalid_type() -> None:
    with pytest.raises(ValidationError):
        EquipmentSchema(equipment_id="x", mine_id="m1", equipment_type="bicycle")  # type: ignore[arg-type]


def test_activity_basic() -> None:
    a = RawEquipmentActivitySchema(
        equipment_id="Truck_17",
        timestamp=datetime.now(UTC),
        activity_type="hauling",
        zone_id="Haul_Road_C",
        speed_kmh=31.0,
    )
    assert a.activity_type == "hauling"


def test_activity_default_payload_is_empty_dict() -> None:
    a = RawEquipmentActivitySchema(
        equipment_id="Truck_17",
        timestamp=datetime.now(UTC),
        activity_type="idle",
    )
    assert a.raw_payload == {}
