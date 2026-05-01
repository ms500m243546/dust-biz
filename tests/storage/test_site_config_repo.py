from sqlalchemy.orm import Session

from app.storage.models import Mine
from app.storage.repositories.site_config import SiteConfigRepository


def _seed_mine(session: Session) -> None:
    session.add(Mine(mine_id="m1", name="Demo"))
    session.flush()


def test_upsert_creates_then_updates(session: Session) -> None:
    _seed_mine(session)
    repo = SiteConfigRepository(session)

    created = repo.upsert(
        site_id="m1-main",
        mine_id="m1",
        automation_level="L1",
        pm10_thresholds={"warning": 100.0, "breach": 150.0},
        pm25_thresholds={"warning": 25.0, "breach": 35.0},
        extreme_breach_threshold=0.85,
        low_confidence_threshold=0.5,
        optimization_weights={"w_breach": 1.0},
    )
    assert created.site_id == "m1-main"
    assert created.automation_level == "L1"

    updated = repo.upsert(
        site_id="m1-main",
        mine_id="m1",
        automation_level="L2",
        pm10_thresholds={"warning": 80.0, "breach": 130.0},
        pm25_thresholds={"warning": 20.0, "breach": 30.0},
        extreme_breach_threshold=0.9,
        low_confidence_threshold=0.6,
        optimization_weights={"w_breach": 2.0},
        updated_by="env_mgr",
    )
    assert updated.automation_level == "L2"
    assert updated.pm10_thresholds["warning"] == 80.0
    assert updated.updated_by == "env_mgr"


def test_get_for_mine_returns_only_that_mine(session: Session) -> None:
    _seed_mine(session)
    session.add(Mine(mine_id="m2", name="Other"))
    session.flush()
    repo = SiteConfigRepository(session)
    repo.upsert(
        "m1-main",
        "m1",
        "L1",
        {"warning": 100.0, "breach": 150.0},
        {"warning": 25.0, "breach": 35.0},
        0.85,
        0.5,
        {"w_breach": 1.0},
    )
    repo.upsert(
        "m2-main",
        "m2",
        "L1",
        {"warning": 100.0, "breach": 150.0},
        {"warning": 25.0, "breach": 35.0},
        0.85,
        0.5,
        {"w_breach": 1.0},
    )

    m1_only = repo.get_for_mine("m1")
    assert len(m1_only) == 1
    assert m1_only[0].site_id == "m1-main"


def test_get_returns_none_for_missing_id(session: Session) -> None:
    repo = SiteConfigRepository(session)
    assert repo.get("does-not-exist") is None
