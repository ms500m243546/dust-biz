"""Phase X — shared multi-station GBM promotion tests.

Pure-function tests over `decide_shared_promotion`. Verifies the
non-worse + strict-better-on-one criterion against the per-station
baseline. The lifespan-level promotion is exercised separately via
the API smoke + the in-memory training tests.
"""

from __future__ import annotations

from app.training.dust_forecast_training import (
    X_PROMOTION_NONWORSE_TOLERANCE,
    X_PROMOTION_STRICT_MARGIN,
    decide_shared_promotion,
)


def _ps_payload(mae: float) -> dict[str, object]:
    return {
        "ece": 0.01,
        "mae_pm10": mae,
        "observed_count": 500,
        "protocol": {"max_ece": 0.05},
    }


def _shared_payload(*, per_receptor_mae: dict[str, float]) -> dict[str, object]:
    return {
        "ece": 0.01,
        "mae_pm10": sum(per_receptor_mae.values()) / len(per_receptor_mae),
        "observed_count": 500,
        "protocol": {"max_ece": 0.05},
        "per_receptor": {
            sid: {"mae_pm10": mae, "sample_count": 100}
            for sid, mae in per_receptor_mae.items()
        },
    }


def test_shared_promotion_passes_when_strictly_better_everywhere() -> None:
    decision = decide_shared_promotion(
        shared_payload=_shared_payload(
            per_receptor_mae={"a": 8.0, "b": 9.0, "c": 11.0},
        ),
        per_station_payloads={
            "a": _ps_payload(10.0),
            "b": _ps_payload(11.0),
            "c": _ps_payload(13.0),
        },
    )
    assert decision.passed
    assert decision.reasons == ()


def test_shared_promotion_passes_when_one_strict_win_others_tied() -> None:
    decision = decide_shared_promotion(
        shared_payload=_shared_payload(
            per_receptor_mae={"a": 9.9, "b": 11.0, "c": 13.0},
        ),
        per_station_payloads={
            "a": _ps_payload(11.0),  # > X_PROMOTION_STRICT_MARGIN better
            "b": _ps_payload(11.0),
            "c": _ps_payload(13.0),
        },
    )
    assert decision.passed


def test_shared_promotion_blocks_when_regresses_on_one_station() -> None:
    decision = decide_shared_promotion(
        shared_payload=_shared_payload(
            per_receptor_mae={"a": 8.0, "b": 15.0},  # regression on b
        ),
        per_station_payloads={
            "a": _ps_payload(10.0),
            "b": _ps_payload(11.0),
        },
    )
    assert not decision.passed
    assert any("regresses on b" in r for r in decision.reasons)


def test_shared_promotion_blocks_when_only_ties_no_strict_win() -> None:
    # Within tolerance on every station but never strictly better by
    # the strict-margin → hold (engineering churn isn't worth it).
    decision = decide_shared_promotion(
        shared_payload=_shared_payload(
            per_receptor_mae={"a": 10.0, "b": 11.0},
        ),
        per_station_payloads={
            "a": _ps_payload(10.0),
            "b": _ps_payload(11.0),
        },
    )
    assert not decision.passed
    assert any("never strictly better" in r for r in decision.reasons)


def test_shared_promotion_blocks_when_per_station_payload_missing() -> None:
    # Cannot honestly assert non-worse without a comparator on every
    # station shared was evaluated on.
    decision = decide_shared_promotion(
        shared_payload=_shared_payload(
            per_receptor_mae={"a": 8.0, "b": 9.0},
        ),
        per_station_payloads={"a": _ps_payload(10.0)},  # b missing
    )
    assert not decision.passed
    assert any("no per-station payload for b" in r for r in decision.reasons)


def test_shared_promotion_blocks_when_shared_fails_base_gate() -> None:
    payload = _shared_payload(per_receptor_mae={"a": 8.0})
    payload["ece"] = 0.10  # blow past max_ece
    decision = decide_shared_promotion(
        shared_payload=payload,
        per_station_payloads={"a": _ps_payload(10.0)},
    )
    assert not decision.passed
    assert any(r.startswith("shared::") for r in decision.reasons)


def test_shared_promotion_blocks_when_per_receptor_empty() -> None:
    payload = {
        "ece": 0.01,
        "mae_pm10": 8.0,
        "observed_count": 500,
        "protocol": {"max_ece": 0.05},
        "per_receptor": {},
    }
    decision = decide_shared_promotion(
        shared_payload=payload,
        per_station_payloads={"a": _ps_payload(10.0)},
    )
    assert not decision.passed
    assert any("empty per_receptor" in r for r in decision.reasons)


def test_strict_margin_constants_are_sensible() -> None:
    # Documented invariants — neither constant should drift to absurd
    # values without an explicit phase change.
    assert 0.0 < X_PROMOTION_STRICT_MARGIN <= 5.0
    assert 0.0 < X_PROMOTION_NONWORSE_TOLERANCE <= 5.0
