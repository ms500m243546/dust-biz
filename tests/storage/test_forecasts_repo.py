from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.storage.models import DustPrediction
from app.storage.repositories.forecasts import DustPredictionRepository

T0 = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)


def _make(prediction_id: str, t: datetime, target_id: str = "haul_c") -> DustPrediction:
    return DustPrediction(
        prediction_id=prediction_id,
        issued_at=t.replace(tzinfo=None),
        target_kind="zone",
        target_id=target_id,
        forecast_horizon="60min",
        predicted_pm10=120.0,
        predicted_pm25=42.0,
        breach_probability=0.45,
        confidence=0.72,
        main_risk_window="12:00-13:00",
        main_uncertainty="stable",
        model_version="dust_forecast_heuristic_v0.1.0",
        feature_pipeline_version="feature_pipeline_v0.1.0",
        input_data_quality_score=0.9,
        data_quality_warnings=[],
        source="model",
        input_record_ids=["sr-1"],
    )


def test_add_and_latest_for_target(session: Session) -> None:
    repo = DustPredictionRepository(session)
    repo.add(_make("PRED-20260501-0001", T0))
    repo.add(_make("PRED-20260501-0002", T0 + timedelta(minutes=5)))
    latest = repo.latest_for_target("zone", "haul_c")
    assert latest is not None
    assert latest.prediction_id == "PRED-20260501-0002"


def test_get_recent_filters_by_target_and_window(session: Session) -> None:
    repo = DustPredictionRepository(session)
    repo.add(_make("PRED-20260501-0001", T0 - timedelta(hours=2)))
    repo.add(_make("PRED-20260501-0002", T0 - timedelta(minutes=10)))
    repo.add(_make("PRED-20260501-0003", T0, target_id="other_zone"))
    rows = repo.get_recent("zone", "haul_c", since=(T0 - timedelta(hours=1)).replace(tzinfo=None))
    assert {r.prediction_id for r in rows} == {"PRED-20260501-0002"}


def test_next_prediction_id_resets_per_day(session: Session) -> None:
    repo = DustPredictionRepository(session)
    repo.add(_make("PRED-20260501-0001", T0))
    repo.add(_make("PRED-20260501-0002", T0 + timedelta(minutes=1)))
    assert repo.next_prediction_id(T0.date()) == "PRED-20260501-0003"
    assert repo.next_prediction_id((T0 + timedelta(days=1)).date()) == "PRED-20260502-0001"


def test_latest_for_target_filters_by_horizon(session: Session) -> None:
    repo = DustPredictionRepository(session)
    fifteen = _make("PRED-20260501-0001", T0)
    fifteen.forecast_horizon = "15min"
    sixty = _make("PRED-20260501-0002", T0 + timedelta(minutes=1))
    sixty.forecast_horizon = "60min"
    repo.add(fifteen)
    repo.add(sixty)
    out_15 = repo.latest_for_target("zone", "haul_c", horizon="15min")
    out_60 = repo.latest_for_target("zone", "haul_c", horizon="60min")
    assert out_15 is not None and out_15.forecast_horizon == "15min"
    assert out_60 is not None and out_60.forecast_horizon == "60min"
