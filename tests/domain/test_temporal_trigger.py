"""Phase AC — temporal trigger tests."""

from __future__ import annotations

from app.domain.temporal_trigger import (
    ACT_NOW_THRESHOLD_MINUTES,
    ForecastTrackPoint,
    decide_trigger_time,
    synthesize_flat_track,
)


def _track(*pairs: tuple[int, float]) -> list[ForecastTrackPoint]:
    return [ForecastTrackPoint(minutes_ahead=t, breach_probability=p) for t, p in pairs]


def test_act_now_when_peak_is_at_t_zero() -> None:
    out = decide_trigger_time(
        forecast_track=_track((0, 0.9), (30, 0.5), (60, 0.3)),
        time_to_effect_minutes=10,
    )
    assert out.act_now is True
    assert out.minutes_from_now == 0
    assert out.peak_minutes_ahead == 0


def test_wait_when_peak_is_in_the_future() -> None:
    # Peak at t=60, time_to_effect=10, duration default 30.
    # Recommended start = max(0, 60 - 10 - 15) = 35 min
    out = decide_trigger_time(
        forecast_track=_track((0, 0.2), (30, 0.4), (60, 0.9), (120, 0.3)),
        time_to_effect_minutes=10,
    )
    assert out.act_now is False
    assert out.minutes_from_now == 35
    assert out.peak_minutes_ahead == 60


def test_act_now_when_peak_close_but_long_ramp() -> None:
    # Peak at t=15, time_to_effect=20. Desired start = -20 → clamped to 0
    # → falls below ACT_NOW_THRESHOLD (5 min).
    out = decide_trigger_time(
        forecast_track=_track((0, 0.4), (15, 0.85), (60, 0.3)),
        time_to_effect_minutes=20,
    )
    assert out.act_now is True


def test_empty_track_collapses_to_act_now() -> None:
    out = decide_trigger_time(
        forecast_track=[],
        time_to_effect_minutes=10,
    )
    assert out.act_now is True
    assert out.minutes_from_now == 0
    assert "empty" in out.reason


def test_flat_track_collapses_to_act_now() -> None:
    out = decide_trigger_time(
        forecast_track=synthesize_flat_track(breach_probability=0.6),
        time_to_effect_minutes=10,
    )
    # Synthetic flat track has equal probabilities; max() picks the
    # first element (t=0). Decision collapses to act_now.
    assert out.act_now is True
    assert out.peak_minutes_ahead == 0


def test_negative_time_to_effect_treated_as_zero() -> None:
    out = decide_trigger_time(
        forecast_track=_track((0, 0.3), (60, 0.9)),
        time_to_effect_minutes=-5,
    )
    # Recommended start = max(0, 60 - 0 - 15) = 45
    assert out.minutes_from_now == 45


def test_act_now_threshold_constant_is_sane() -> None:
    assert 0 <= ACT_NOW_THRESHOLD_MINUTES <= 30


def test_synthesize_flat_track_clamps_probability() -> None:
    track = synthesize_flat_track(breach_probability=1.5)
    assert all(p.breach_probability == 1.0 for p in track)
    track = synthesize_flat_track(breach_probability=-0.2)
    assert all(p.breach_probability == 0.0 for p in track)
