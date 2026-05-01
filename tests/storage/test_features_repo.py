from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.storage.models import FeatureRecord, Mine, Zone
from app.storage.repositories.features import FeatureRepository


def _seed(session: Session) -> None:
    session.add(Mine(mine_id="m1", name="Demo"))
    session.add(
        Zone(
            zone_id="z1",
            mine_id="m1",
            zone_type="haul_road",
            operational_importance="high",
            dust_generation_baseline="medium",
        )
    )
    session.flush()


def _make(
    zone_id: str, t: datetime, payload: dict[str, object] | None = None
) -> FeatureRecord:
    return FeatureRecord(
        timestamp=t,
        zone_id=zone_id,
        feature_pipeline_version="feature_pipeline_v0.1.0",
        feature_payload=payload or {"pm.pm10_avg_15min": 42.0},
        missing_inputs=[],
    )


def test_add_and_latest_for_zone(session: Session) -> None:
    _seed(session)
    repo = FeatureRepository(session)
    t0 = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    repo.add(_make("z1", t0))
    repo.add(_make("z1", t0 + timedelta(minutes=5), payload={"pm.pm10_avg_15min": 99.0}))
    latest = repo.latest_for_zone("z1")
    assert latest is not None
    assert latest.feature_payload["pm.pm10_avg_15min"] == 99.0


def test_latest_for_zone_returns_none_when_empty(session: Session) -> None:
    assert FeatureRepository(session).latest_for_zone("missing") is None


def test_get_recent_filters_by_since(session: Session) -> None:
    _seed(session)
    repo = FeatureRepository(session)
    t0 = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    repo.add(_make("z1", t0 - timedelta(minutes=120)))
    repo.add(_make("z1", t0 - timedelta(minutes=10)))
    repo.add(_make("z1", t0))
    recent = repo.get_recent("z1", since=t0 - timedelta(minutes=30))
    assert len(recent) == 2
