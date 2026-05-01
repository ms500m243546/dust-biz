from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.storage.models import Mine, MineStateSnapshot, Zone
from app.storage.repositories.mine_state import MineStateSnapshotRepository


def _seed_mine_with_zone(session: Session, mine_id: str, zone_id: str) -> None:
    session.add(Mine(mine_id=mine_id, name=f"Demo {mine_id}"))
    session.add(
        Zone(
            zone_id=zone_id,
            mine_id=mine_id,
            zone_type="haul_road",
            operational_importance="high",
            dust_generation_baseline="medium",
        )
    )
    session.flush()


def _make_snapshot(zone_id: str, t: datetime, activity: str = "hauling") -> MineStateSnapshot:
    return MineStateSnapshot(
        timestamp=t,
        zone_id=zone_id,
        activity=activity,
        equipment_active=[],
        production_rate_tph=None,
        dust_generation_potential="medium",
        wind_exposure="medium",
        downwind_assets=[],
        operational_importance="high",
        staleness_flags=[],
    )


def test_add_and_latest_for_zone(session: Session) -> None:
    _seed_mine_with_zone(session, "m1", "z1")
    repo = MineStateSnapshotRepository(session)
    t0 = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    repo.add(_make_snapshot("z1", t0))
    repo.add(_make_snapshot("z1", t0 + timedelta(minutes=5), activity="loading"))
    latest = repo.latest_for_zone("z1")
    assert latest is not None
    assert latest.activity == "loading"


def test_latest_for_mine_returns_one_per_zone(session: Session) -> None:
    _seed_mine_with_zone(session, "m1", "z1")
    session.add(
        Zone(
            zone_id="z2",
            mine_id="m1",
            zone_type="pit",
            operational_importance="critical",
            dust_generation_baseline="high",
        )
    )
    session.flush()
    repo = MineStateSnapshotRepository(session)
    t0 = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    repo.add(_make_snapshot("z1", t0))
    repo.add(_make_snapshot("z2", t0 + timedelta(minutes=1)))
    out = repo.latest_for_mine("m1")
    assert sorted(s.zone_id for s in out) == ["z1", "z2"]


def test_latest_for_zone_returns_none_when_empty(session: Session) -> None:
    assert MineStateSnapshotRepository(session).latest_for_zone("nope") is None
