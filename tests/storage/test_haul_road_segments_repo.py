from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.storage.models import Mine
from app.storage.repositories.haul_road_segments import HaulRoadSegmentRepository


def _seed_mine(session: Session, mine_id: str = "m1") -> None:
    session.add(Mine(mine_id=mine_id, name=f"Demo {mine_id}"))
    session.flush()


def test_upsert_creates_then_updates(session: Session) -> None:
    _seed_mine(session)
    repo = HaulRoadSegmentRepository(session)

    seg = repo.upsert(
        segment_id="seg1",
        mine_id="m1",
        from_node="z1",
        to_node="z2",
        length_m=420.0,
        surface_type="gravel",
    )
    assert seg.length_m == 420.0
    assert seg.last_watered_at is None

    updated = repo.upsert(
        segment_id="seg1",
        mine_id="m1",
        from_node="z1",
        to_node="z3",
        length_m=510.0,
        surface_type="gravel",
    )
    assert updated.to_node == "z3"
    assert updated.length_m == 510.0


def test_mark_watered_sets_timestamp(session: Session) -> None:
    _seed_mine(session)
    repo = HaulRoadSegmentRepository(session)
    repo.upsert("seg1", "m1", "z1", "z2", 420.0, "gravel")
    now = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    seg = repo.mark_watered("seg1", now)
    assert seg is not None
    assert seg.last_watered_at == now.replace(tzinfo=None) or seg.last_watered_at == now


def test_mark_watered_returns_none_for_missing(session: Session) -> None:
    repo = HaulRoadSegmentRepository(session)
    assert repo.mark_watered("ghost", datetime.now(UTC)) is None


def test_get_for_mine_filters(session: Session) -> None:
    _seed_mine(session, "m1")
    _seed_mine(session, "m2")
    repo = HaulRoadSegmentRepository(session)
    repo.upsert("seg1", "m1", "z1", "z2", 100.0, "gravel")
    repo.upsert("seg2", "m2", "z3", "z4", 200.0, "gravel")
    only_m1 = repo.get_for_mine("m1")
    assert [s.segment_id for s in only_m1] == ["seg1"]
