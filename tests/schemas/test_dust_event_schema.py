from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.dust_events import DustEventCreate, DustEventSchema


def _create_payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "detected_at": datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
        "affected_station": "cs1",
        "peak_pm10": 180.0,
        "peak_pm25": 70.0,
        "breach_occurred": True,
        "event_source": "manual_entry",
    }
    base.update(overrides)
    return base


def test_dust_event_create_round_trip() -> None:
    p = DustEventCreate(**_create_payload())  # type: ignore[arg-type]
    assert p.affected_station == "cs1"
    assert p.event_source == "manual_entry"
    assert p.linked_prediction_ids == []


def test_dust_event_source_enum_validated() -> None:
    DustEventCreate(**_create_payload(event_source="threshold_trigger"))  # type: ignore[arg-type]
    DustEventCreate(**_create_payload(event_source="model_alert"))  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        DustEventCreate(**_create_payload(event_source="oracle"))  # type: ignore[arg-type]


def test_dust_event_pm_must_be_non_negative() -> None:
    with pytest.raises(ValidationError):
        DustEventCreate(**_create_payload(peak_pm10=-1.0))  # type: ignore[arg-type]


def test_dust_event_schema_round_trip() -> None:
    s = DustEventSchema(
        event_id="EVT-20260501-001",
        detected_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
        affected_station="cs1",
        peak_pm10=180.0,
        peak_pm25=70.0,
        breach_occurred=True,
        event_source="manual_entry",
        linked_prediction_ids=["PRED-20260501-0001"],
        notes="visible plume from boundary station",
    )
    assert s.event_id == "EVT-20260501-001"
    assert s.linked_prediction_ids == ["PRED-20260501-0001"]
