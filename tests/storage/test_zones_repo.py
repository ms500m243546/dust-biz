from sqlalchemy.orm import Session

from app.storage.models import Mine
from app.storage.repositories.zones import ZoneRepository


def _seed_mine(session: Session, mine_id: str = "m1") -> None:
    session.add(Mine(mine_id=mine_id, name=f"Demo {mine_id}"))
    session.flush()


def test_upsert_creates_then_updates(session: Session) -> None:
    _seed_mine(session)
    repo = ZoneRepository(session)

    created = repo.upsert(
        zone_id="z1",
        mine_id="m1",
        zone_type="haul_road",
        operational_importance="high",
        dust_generation_baseline="medium",
    )
    assert created.zone_id == "z1"
    assert created.allowed_interventions == []

    updated = repo.upsert(
        zone_id="z1",
        mine_id="m1",
        zone_type="haul_road",
        operational_importance="critical",
        dust_generation_baseline="high",
        allowed_interventions=["reduce_speed", "water_road"],
        requires_approval_for=["reroute"],
    )
    assert updated.operational_importance == "critical"
    assert "water_road" in updated.allowed_interventions


def test_get_for_mine_filters(session: Session) -> None:
    _seed_mine(session, "m1")
    _seed_mine(session, "m2")
    repo = ZoneRepository(session)
    repo.upsert("z1", "m1", "pit", "high", "high")
    repo.upsert("z2", "m2", "pit", "medium", "medium")
    only_m1 = repo.get_for_mine("m1")
    assert [z.zone_id for z in only_m1] == ["z1"]


def test_get_returns_none_for_missing(session: Session) -> None:
    assert ZoneRepository(session).get("nope") is None
