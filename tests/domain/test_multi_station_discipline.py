"""Phase Q.3 — multi-station discipline (B-5/B-6/B-14) tests.

Pure-function tests over `_multi_station_caveats` and end-to-end
checks that `compute_metric_payload` surfaces the three caveat
fields on both return branches.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.domain.evaluation_protocol import EvaluationProtocol
from app.domain.model_performance import (
    MIN_RECEPTORS_FOR_NO_SURVIVOR_CAVEAT,
    RECEPTOR_TO_MINE,
    _multi_station_caveats,
    compute_metric_payload,
)
from app.schemas.model_performance import TrainingRecordSchema


def _proto() -> EvaluationProtocol:
    start = datetime(2025, 5, 3)
    return EvaluationProtocol(
        split_strategy="walk_forward",
        train_window_from=start,
        train_window_to=start + timedelta(days=140),
        validation_window_from=start + timedelta(days=147),
        validation_window_to=start + timedelta(days=170),
        test_window_from=start + timedelta(days=177),
        test_window_to=start + timedelta(days=200),
        embargo_days=7,
        sealed_test_used=True,
        feature_set=("pm10_lag_1h",),
        required_covariates=(),
        forbidden_covariates=(),
    )


def _record(target_id: str, *, predicted_pm10: float = 50.0, actual: float = 50.0) -> TrainingRecordSchema:
    # Predicted breach probability matches actual outcome — keeps ECE
    # at 0 so the M.4.1 gate doesn't reject these synthetic rows.
    return TrainingRecordSchema(
        prediction_id=f"r::{target_id}::{actual}",
        issued_at=datetime(2026, 4, 5, 12, 0),
        target_kind="sensor",
        target_id=target_id,
        forecast_horizon="60min",
        predicted_pm10=predicted_pm10,
        predicted_pm25=0.0,
        predicted_breach_probability=1.0 if actual >= 150.0 else 0.0,
        confidence=0.7,
        model_version="dust_forecast_gbm_v0.1.0",
        human_action="no_recommendation",
        actual_pm10_peak=actual,
        breach_occurred=actual >= 150.0,
        outcome_status="observed",
        recorded_at=datetime(2026, 4, 5, 12, 0),
    )


def test_caveats_survivor_fires_when_below_threshold() -> None:
    survivor, _, _ = _multi_station_caveats(
        per_receptor={"only-one": {}},
        station_count=5,
        trained_on_mine=None,
    )
    assert survivor is not None
    assert "B-5" in survivor


def test_caveats_survivor_silent_when_full_coverage() -> None:
    survivor, _, _ = _multi_station_caveats(
        per_receptor={"a": {}, "b": {}},
        station_count=2,
        trained_on_mine=None,
    )
    assert survivor is None


def test_caveats_selection_fires_on_single_mine() -> None:
    # Both receptors at the same mine.
    _, selection, _ = _multi_station_caveats(
        per_receptor={"chq-club-23-marzo": {}, "chq-calama-centro": {}},
        station_count=2,
        trained_on_mine=None,
    )
    assert selection is not None
    assert "B-6" in selection


def test_caveats_selection_silent_with_two_mines() -> None:
    _, selection, _ = _multi_station_caveats(
        per_receptor={"chq-club-23-marzo": {}, "lp-em05-cuncumen": {}},
        station_count=2,
        trained_on_mine=None,
    )
    assert selection is None


def test_caveats_cross_mine_block_appears_when_trained_elsewhere() -> None:
    _, _, cross = _multi_station_caveats(
        per_receptor={"lp-em05-cuncumen": {}, "lb-las-condes": {}},
        station_count=2,
        trained_on_mine="los-pelambres",
    )
    assert cross is not None
    assert cross["trained_on_mine"] == "los-pelambres"
    assert "los-bronces" in cross["evaluated_on_mines"]
    assert "lb-las-condes" in cross["cross_mine_receptors"]
    assert "B-14" in cross["warning"]


def test_caveats_cross_mine_silent_when_in_sample_only() -> None:
    _, _, cross = _multi_station_caveats(
        per_receptor={"lp-em05-cuncumen": {}},
        station_count=1,
        trained_on_mine="los-pelambres",
    )
    assert cross is None


def test_caveats_cross_mine_silent_when_trained_on_unspecified() -> None:
    _, _, cross = _multi_station_caveats(
        per_receptor={"lp-em05-cuncumen": {}, "lb-las-condes": {}},
        station_count=2,
        trained_on_mine=None,
    )
    assert cross is None


def test_compute_metric_payload_emits_caveats_on_observed_path() -> None:
    records = [
        _record("lp-em05-cuncumen", predicted_pm10=40, actual=42),
        _record("lb-las-condes", predicted_pm10=55, actual=50),
    ]
    payload = compute_metric_payload(
        records,
        protocol=_proto(),
        station_count=5,
        trained_on_mine="los-pelambres",
    )
    assert "survivor_caveat" in payload
    assert "selection_caveat" in payload
    assert "cross_mine_eval" in payload
    # Survivor: 2 < 5 → caveat fires.
    assert payload["survivor_caveat"] is not None
    # Selection: spans 2 mines → silent.
    assert payload["selection_caveat"] is None
    # Cross-mine: trained on los-pelambres, evaluated on lb-las-condes too.
    assert payload["cross_mine_eval"] is not None


def test_compute_metric_payload_emits_caveats_on_empty_path() -> None:
    # No observed records — empty branch must still emit the keys.
    payload = compute_metric_payload(
        [],
        protocol=_proto(),
        station_count=5,
        trained_on_mine="los-pelambres",
    )
    assert "survivor_caveat" in payload
    assert "selection_caveat" in payload
    assert "cross_mine_eval" in payload


def test_receptor_to_mine_includes_q1_roster() -> None:
    # Sanity — every roster station must be classified for the
    # selection-caveat logic to work.
    expected = {
        "lp-em05-cuncumen",
        "lb-las-condes",
        "chq-club-23-marzo",
        "chq-calama-centro",
        "cnt-sierra-gorda",
    }
    assert expected.issubset(RECEPTOR_TO_MINE.keys())


def test_min_receptors_constant_documented() -> None:
    # Defensive: if this drops to 1, the survivor caveat stops firing
    # on multi-station evaluations and the validator will complain.
    assert MIN_RECEPTORS_FOR_NO_SURVIVOR_CAVEAT >= 2
