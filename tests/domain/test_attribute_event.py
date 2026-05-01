from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.domain.attribution import EventNotFoundError, attribute_event
from app.models import registry
from app.models.attribution.rules_baseline import RulesBaselineAttributor
from app.storage.models import (
    DustEvent,
    Equipment,
    EquipmentActivity,
    Mine,
    Sensor,
    SensorReading,
    SourceAttribution,
    WeatherReading,
    Zone,
)

NOW = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _reset_registry() -> Iterator[None]:
    registry.reset()
    registry.register(RulesBaselineAttributor())
    yield
    registry.reset()


def _seed(session: Session, *, with_activity: bool = True) -> str:
    session.add(Mine(mine_id="m1", name="Demo"))
    session.add(
        Zone(
            zone_id="haul_c",
            mine_id="m1",
            zone_type="haul_road",
            operational_importance="high",
            dust_generation_baseline="high",
        )
    )
    session.add(
        Zone(
            zone_id="idle_pit",
            mine_id="m1",
            zone_type="pit",
            operational_importance="medium",
            dust_generation_baseline="low",
        )
    )
    session.add(Sensor(sensor_id="cs1", mine_id="m1", zone_id="haul_c", sensor_type="pm10"))
    session.add(Equipment(equipment_id="truck_1", mine_id="m1", equipment_type="truck"))
    session.flush()

    detected_at = (NOW - timedelta(minutes=5)).replace(tzinfo=None)
    if with_activity:
        for i in range(6):
            session.add(
                EquipmentActivity(
                    equipment_id="truck_1",
                    timestamp=detected_at - timedelta(minutes=2 + i),
                    zone_id="haul_c",
                    activity_type="hauling",
                    tonnage=100.0,
                    raw_payload={},
                )
            )
    # Rising PM at the affected station
    for mins_ago, pm10 in [(28, 60.0), (22, 70.0), (12, 110.0), (4, 160.0)]:
        session.add(
            SensorReading(
                sensor_id="cs1",
                timestamp=detected_at - timedelta(minutes=mins_ago),
                raw_value={"pm10_ugm3": pm10, "pm25_ugm3": pm10 * 0.4},
            )
        )
    session.add(
        WeatherReading(
            source="onsite",
            zone_id=None,
            timestamp=detected_at - timedelta(minutes=2),
            wind_speed_ms=4.0,
            wind_direction_deg=180.0,
        )
    )
    session.add(
        DustEvent(
            event_id="EVT-20260501-001",
            detected_at=detected_at,
            affected_station="cs1",
            peak_pm10=160.0,
            peak_pm25=64.0,
            breach_occurred=True,
            event_source="manual_entry",
            linked_prediction_ids=[],
            notes="visible plume",
        )
    )
    session.flush()
    return "EVT-20260501-001"


def test_attribute_event_persists_attribution_with_safety_fields(session: Session) -> None:
    event_id = _seed(session)
    out = attribute_event(session=session, dust_event_id=event_id, now=NOW)
    assert out.dust_event_id == event_id
    assert out.model_version.startswith("source_attribution_rules_")
    assert 0.0 <= out.confidence <= 1.0

    rows = list(session.query(SourceAttribution).all())
    assert len(rows) == 1
    assert rows[0].attribution_id == out.attribution_id


def test_unknown_event_raises(session: Session) -> None:
    with pytest.raises(EventNotFoundError):
        attribute_event(session=session, dust_event_id="EVT-ghost", now=NOW)


def test_active_dust_zone_outranks_idle_zone(session: Session) -> None:
    event_id = _seed(session)
    out = attribute_event(session=session, dust_event_id=event_id, now=NOW)
    sources = [p.source for p in out.probable_sources]
    haul_idx = sources.index("haul_c")
    idle_idx = sources.index("idle_pit")
    assert haul_idx < idle_idx


def test_no_activity_is_reflected_in_evidence(session: Session) -> None:
    event_id = _seed(session, with_activity=False)
    out = attribute_event(session=session, dust_event_id=event_id, now=NOW)
    # No equipment activity anywhere -> all activity_intensities are 0,
    # but other signals (PM rise, wind, baseline dust potential) still
    # contribute, so the model can produce a confident attribution.
    # The contract here is that the evidence honestly records the
    # zero-activity situation for reviewer audit.
    intensities = out.evidence_fields["activity_intensities"]
    assert all(v == 0.0 for v in intensities.values())


def test_attribution_records_evidence_for_review(session: Session) -> None:
    event_id = _seed(session)
    out = attribute_event(session=session, dust_event_id=event_id, now=NOW)
    assert "candidate_count" in out.evidence_fields
    assert out.evidence_fields["candidate_count"] == 2
    assert "concurrent_pm_rises" in out.evidence_fields


def test_re_attributing_appends_to_history(session: Session) -> None:
    event_id = _seed(session)
    first = attribute_event(session=session, dust_event_id=event_id, now=NOW)
    second = attribute_event(
        session=session, dust_event_id=event_id, now=NOW + timedelta(minutes=10)
    )
    assert first.attribution_id != second.attribution_id
    rows = list(session.query(SourceAttribution).all())
    assert len(rows) == 2
