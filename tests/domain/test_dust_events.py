from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.domain.dust_events import (
    UnknownStationError,
    record_manual_event,
    trigger_events_from_forecasts,
)
from app.schemas.dust_events import DustEventCreate
from app.storage.models import DustPrediction, Mine, Sensor

NOW = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)


def _seed_sensor(session: Session) -> None:
    session.add(Mine(mine_id="m1", name="Demo"))
    session.add(Sensor(sensor_id="cs1", mine_id="m1", sensor_type="pm10"))
    session.flush()


def _prediction(
    pid: str, *, mins_ago: float, breach: float, target: str = "cs1"
) -> DustPrediction:
    return DustPrediction(
        prediction_id=pid,
        issued_at=(NOW - timedelta(minutes=mins_ago)).replace(tzinfo=None),
        target_kind="sensor",
        target_id=target,
        forecast_horizon="60min",
        predicted_pm10=160.0,
        predicted_pm25=60.0,
        breach_probability=breach,
        confidence=0.8,
        main_risk_window="12:00-13:00",
        main_uncertainty="stable",
        model_version="dust_forecast_heuristic_v0.1.0",
        feature_pipeline_version="feature_pipeline_v0.1.0",
        input_data_quality_score=0.9,
        data_quality_warnings=[],
        source="model",
        input_record_ids=[],
    )


def test_record_manual_event_assigns_id_and_persists(session: Session) -> None:
    _seed_sensor(session)
    out = record_manual_event(
        session=session,
        payload=DustEventCreate(
            detected_at=NOW,
            affected_station="cs1",
            peak_pm10=180.0,
            peak_pm25=70.0,
            breach_occurred=True,
            notes="visible plume",
        ),
    )
    assert out.event_id == "EVT-20260501-001"
    assert out.event_source == "manual_entry"


def test_record_manual_event_unknown_station_raises(session: Session) -> None:
    _seed_sensor(session)
    with pytest.raises(UnknownStationError):
        record_manual_event(
            session=session,
            payload=DustEventCreate(
                detected_at=NOW,
                affected_station="ghost",
                peak_pm10=100.0,
                peak_pm25=40.0,
            ),
        )


def test_trigger_no_crossing_predictions_returns_empty(session: Session) -> None:
    _seed_sensor(session)
    session.add(_prediction("PRED-1", mins_ago=10, breach=0.4))
    session.flush()
    out = trigger_events_from_forecasts(session=session, sensor_id="cs1", now=NOW)
    assert out == []


def test_trigger_creates_one_event_with_linked_predictions(session: Session) -> None:
    _seed_sensor(session)
    session.add(_prediction("PRED-1", mins_ago=10, breach=0.75))
    session.add(_prediction("PRED-2", mins_ago=5, breach=0.9))
    session.flush()

    out = trigger_events_from_forecasts(session=session, sensor_id="cs1", now=NOW)
    assert len(out) == 1
    event = out[0]
    assert event.event_source == "threshold_trigger"
    assert set(event.linked_prediction_ids) == {"PRED-1", "PRED-2"}
    assert event.breach_occurred is True  # one prediction had breach >= 0.85


def test_trigger_is_idempotent_per_day(session: Session) -> None:
    _seed_sensor(session)
    session.add(_prediction("PRED-1", mins_ago=10, breach=0.75))
    session.flush()
    first = trigger_events_from_forecasts(session=session, sensor_id="cs1", now=NOW)

    # New crossing prediction lands later the same day.
    session.add(_prediction("PRED-2", mins_ago=2, breach=0.8))
    session.flush()
    second = trigger_events_from_forecasts(session=session, sensor_id="cs1", now=NOW)

    assert len(second) == 1
    assert second[0].event_id == first[0].event_id
    assert set(second[0].linked_prediction_ids) == {"PRED-1", "PRED-2"}


def test_trigger_unknown_sensor_raises(session: Session) -> None:
    with pytest.raises(UnknownStationError):
        trigger_events_from_forecasts(session=session, sensor_id="ghost", now=NOW)
