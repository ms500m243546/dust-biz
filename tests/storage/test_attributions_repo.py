from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.storage.models import DustEvent, Mine, Sensor, SourceAttribution
from app.storage.repositories.attributions import SourceAttributionRepository

T0 = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)


def _seed(session: Session) -> None:
    session.add(Mine(mine_id="m1", name="Demo"))
    session.add(Sensor(sensor_id="cs1", mine_id="m1", sensor_type="pm10"))
    session.flush()
    session.add(
        DustEvent(
            event_id="EVT-20260501-001",
            detected_at=T0.replace(tzinfo=None),
            affected_station="cs1",
            peak_pm10=180.0,
            peak_pm25=70.0,
            breach_occurred=True,
            event_source="manual_entry",
            linked_prediction_ids=[],
            notes=None,
        )
    )
    session.flush()


def _make(aid: str, t: datetime, event_id: str = "EVT-20260501-001") -> SourceAttribution:
    return SourceAttribution(
        attribution_id=aid,
        dust_event_id=event_id,
        issued_at=t.replace(tzinfo=None),
        affected_station="cs1",
        probable_sources=[
            {"source": "haul_c", "confidence": 0.6, "reason": "wind"},
        ],
        evidence_fields={},
        confidence=0.7,
        model_version="source_attribution_rules_v0.1.0",
    )


def test_add_and_latest_for_event(session: Session) -> None:
    _seed(session)
    repo = SourceAttributionRepository(session)
    repo.add(_make("ATTR-20260501-001", T0))
    repo.add(_make("ATTR-20260501-002", T0 + timedelta(minutes=5)))
    out = repo.latest_for_event("EVT-20260501-001")
    assert out is not None
    assert out.attribution_id == "ATTR-20260501-002"


def test_history_for_event_returns_all_attempts(session: Session) -> None:
    _seed(session)
    repo = SourceAttributionRepository(session)
    repo.add(_make("ATTR-20260501-001", T0))
    repo.add(_make("ATTR-20260501-002", T0 + timedelta(minutes=5)))
    history = repo.history_for_event("EVT-20260501-001")
    assert [h.attribution_id for h in history] == [
        "ATTR-20260501-002",
        "ATTR-20260501-001",
    ]


def test_next_attribution_id_resets_per_day(session: Session) -> None:
    _seed(session)
    repo = SourceAttributionRepository(session)
    repo.add(_make("ATTR-20260501-001", T0))
    assert repo.next_attribution_id(T0.date()) == "ATTR-20260501-002"
    assert repo.next_attribution_id((T0 + timedelta(days=1)).date()) == "ATTR-20260502-001"


def test_get_recent_filters_by_window(session: Session) -> None:
    _seed(session)
    repo = SourceAttributionRepository(session)
    repo.add(_make("ATTR-20260501-001", T0 - timedelta(hours=2)))
    repo.add(_make("ATTR-20260501-002", T0 - timedelta(minutes=10)))
    rows = repo.get_recent(since=(T0 - timedelta(hours=1)).replace(tzinfo=None))
    assert {r.attribution_id for r in rows} == {"ATTR-20260501-002"}
