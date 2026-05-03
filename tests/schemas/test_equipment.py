from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.equipment import EquipmentSchema, RawEquipmentActivitySchema


def test_equipment_basic() -> None:
    e = EquipmentSchema(
        equipment_id="Truck_17", mine_id="m1", equipment_type="truck", nominal_capacity_t=240.0
    )
    assert e.equipment_type == "truck"


def test_equipment_truck_geometry_optional() -> None:
    # Phase O.1 — AP-42 inputs are nullable; legacy callers must keep working.
    e = EquipmentSchema(equipment_id="t1", mine_id="m1", equipment_type="truck")
    assert e.empty_weight_tonnes is None
    assert e.tire_contact_area_m2 is None
    assert e.tire_count is None
    assert e.axle_count is None


def test_equipment_truck_geometry_populated() -> None:
    # Komatsu 930E haul truck: ~199 t empty, ~290 t payload, 6 tires.
    e = EquipmentSchema(
        equipment_id="Truck_17",
        mine_id="m1",
        equipment_type="truck",
        nominal_capacity_t=290.0,
        empty_weight_tonnes=199.0,
        tire_contact_area_m2=4.5,
        tire_count=6,
        axle_count=2,
    )
    assert e.empty_weight_tonnes == 199.0
    assert e.tire_count == 6


def test_equipment_truck_geometry_rejects_negative() -> None:
    with pytest.raises(ValidationError):
        EquipmentSchema(
            equipment_id="t1", mine_id="m1", equipment_type="truck",
            empty_weight_tonnes=-5.0,
        )
    with pytest.raises(ValidationError):
        EquipmentSchema(
            equipment_id="t1", mine_id="m1", equipment_type="truck",
            tire_count=-1,
        )


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
