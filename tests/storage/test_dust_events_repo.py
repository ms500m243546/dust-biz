from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.storage.models import DustEvent, Mine, Sensor
from app.storage.repositories.dust_events import DustEventRepository

T0 = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)


def _seed(session: Session) -> None:
    session.add(Mine(mine_id="m1", name="Demo"))
    session.add(Sensor(sensor_id="cs1", mine_id="m1", sensor_type="pm10"))
    session.add(Sensor(sensor_id="cs2", mine_id="m1", sensor_type="pm10"))
    session.flush()


def _make(event_id: str, t: datetime, station: str = "cs1") -> DustEvent:
    return DustEvent(
        event_id=event_id,
        detected_at=t.replace(tzinfo=None),
        affected_station=station,
        peak_pm10=180.0,
        peak_pm25=70.0,
        breach_occurred=True,
        event_source="manual_entry",
        linked_prediction_ids=[],
        notes=None,
    )


def test_add_and_get(session: Session) -> None:
    _seed(session)
    repo = DustEventRepository(session)
    repo.add(_make("EVT-20260501-001", T0))
    out = repo.get("EVT-20260501-001")
    assert out is not None
    assert out.affected_station == "cs1"


def test_get_recent_filters_by_window_and_station(session: Session) -> None:
    _seed(session)
    repo = DustEventRepository(session)
    repo.add(_make("EVT-20260501-001", T0 - timedelta(hours=2)))
    repo.add(_make("EVT-20260501-002", T0 - timedelta(minutes=10)))
    repo.add(_make("EVT-20260501-003", T0, station="cs2"))
    rows = repo.get_recent(since=(T0 - timedelta(hours=1)).replace(tzinfo=None))
    assert len(rows) == 2
    only_cs2 = repo.get_recent(
        since=(T0 - timedelta(hours=3)).replace(tzinfo=None), station="cs2"
    )
    assert {r.event_id for r in only_cs2} == {"EVT-20260501-003"}


def test_next_event_id_resets_per_day(session: Session) -> None:
    _seed(session)
    repo = DustEventRepository(session)
    repo.add(_make("EVT-20260501-001", T0))
    repo.add(_make("EVT-20260501-002", T0 + timedelta(minutes=1)))
    assert repo.next_event_id(T0.date()) == "EVT-20260501-003"
    assert repo.next_event_id((T0 + timedelta(days=1)).date()) == "EVT-20260502-001"
