from datetime import UTC, datetime

from app.schemas.mine_state import MineStateSchema, MineStateZoneSchema
from app.storage.models import MineStateSnapshot


def test_zone_schema_from_orm_with_none_lists_coerces_to_empty() -> None:
    # Construct without flushing - SQLAlchemy `default=list` hasn't fired,
    # so the JSON columns are exposed as None. The schema must coerce.
    snap = MineStateSnapshot(
        timestamp=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
        zone_id="z1",
        activity="hauling",
        dust_generation_potential="medium",
        wind_exposure="medium",
        operational_importance="high",
    )
    out = MineStateZoneSchema.model_validate(snap)
    assert out.equipment_active == []
    assert out.downwind_assets == []
    assert out.staleness_flags == []


def test_aggregate_schema_roundtrip() -> None:
    zone = MineStateZoneSchema(
        timestamp=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
        zone_id="z1",
        activity="loading",
        dust_generation_potential="high",
        wind_exposure="high",
        operational_importance="critical",
    )
    payload = MineStateSchema(
        mine_id="m1",
        computed_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
        window_minutes=15,
        zones=[zone],
    )
    j = payload.model_dump_json()
    rt = MineStateSchema.model_validate_json(j)
    assert rt.zones[0].zone_id == "z1"
    assert rt.window_minutes == 15
