"""Temporal trigger optimization (Phase AC, Tension 4).

Picks *when* an intervention should fire inside the forecast window.
Without this, the ranker assumes "act now" — fine when breach risk is
monotonically rising, but wrong when wind shift, end-of-shift, or a
short rain pulse is about to lower baseline risk on its own.

`decide_trigger_time` is pure: given a forecast track (list of
breach-probability points indexed by minutes-ahead) and an
intervention's time-to-effect, it returns minutes-from-now at which
the action should start so the effect window aligns with the
predicted peak.

This is a first implementation. Smarter variants (continuous
optimization, joint cost-of-waiting) are deferred until multi-horizon
forecasting is wired (`forecasts.gbm` currently emits a single point).
The synthetic-flat track returned by the orchestrator in deferred
mode reduces this to "act now" — which matches the prior single-
point behaviour and is the safest fallback.
"""

from __future__ import annotations

from dataclasses import dataclass

# Default effect-window length used when the catalog does not
# specify one. 30 min covers a typical road-watering pulse + a
# blast-throttle cycle.
DEFAULT_EFFECT_WINDOW_MINUTES = 30
# Below this threshold the trigger is reported as "act now" so the
# orchestrator can collapse a trivial 0–4 minute delay into the
# normal flow without surfacing pointless "wait 3 min" copy.
ACT_NOW_THRESHOLD_MINUTES = 5


@dataclass(frozen=True)
class ForecastTrackPoint:
    """One point on the forecast probability track."""

    minutes_ahead: int
    breach_probability: float


@dataclass(frozen=True)
class TriggerDecision:
    """Result of `decide_trigger_time`.

    `act_now` is True when the recommended start is within
    `ACT_NOW_THRESHOLD_MINUTES`; the orchestrator collapses these
    to the prior immediate-execution behaviour. `peak_minutes_ahead`
    surfaces *why* the decision came out the way it did so the audit
    trail has the supporting numbers, not just the result.
    """

    minutes_from_now: int
    peak_minutes_ahead: int
    peak_breach_probability: float
    act_now: bool
    reason: str


def decide_trigger_time(
    *,
    forecast_track: list[ForecastTrackPoint],
    time_to_effect_minutes: int,
    intervention_duration_minutes: int = DEFAULT_EFFECT_WINDOW_MINUTES,
) -> TriggerDecision:
    """Pick the start time so the effect window centers on the peak.

    Algorithm:
      1. Find `t_peak` — the minutes_ahead with the highest breach
         probability on the track.
      2. Recommend starting at
         `max(0, t_peak - time_to_effect_minutes - duration/2)` so the
         intervention's effect window straddles the peak.
      3. If the resulting start is within ACT_NOW_THRESHOLD_MINUTES,
         flag `act_now=True`.

    Edge cases:
      * Empty track → "act now" with peak=0; no information to defer on.
      * Flat track (degenerate / synthetic) → first point picked as
        peak; result collapses to act now.
      * Negative or NaN time_to_effect → treated as 0.
    """
    if not forecast_track:
        return TriggerDecision(
            minutes_from_now=0,
            peak_minutes_ahead=0,
            peak_breach_probability=0.0,
            act_now=True,
            reason="empty forecast track; defaulting to immediate execution",
        )

    tte = max(0, int(time_to_effect_minutes))
    duration = max(0, int(intervention_duration_minutes))

    peak = max(forecast_track, key=lambda p: p.breach_probability)
    desired_start = peak.minutes_ahead - tte - (duration // 2)
    minutes_from_now = max(0, int(desired_start))
    act_now = minutes_from_now < ACT_NOW_THRESHOLD_MINUTES

    if act_now:
        reason = (
            f"peak risk in {peak.minutes_ahead} min "
            f"(p={peak.breach_probability:.0%}); "
            "act now to align effect window"
        )
    else:
        reason = (
            f"wait {minutes_from_now} min — peak risk in "
            f"{peak.minutes_ahead} min (p={peak.breach_probability:.0%}); "
            f"effect window centers on peak after {tte} min ramp-up"
        )

    return TriggerDecision(
        minutes_from_now=minutes_from_now,
        peak_minutes_ahead=peak.minutes_ahead,
        peak_breach_probability=peak.breach_probability,
        act_now=act_now,
        reason=reason,
    )


def synthesize_flat_track(
    *,
    breach_probability: float,
    horizons_minutes: tuple[int, ...] = (0, 15, 30, 60, 120),
) -> list[ForecastTrackPoint]:
    """Deferred-mode helper.

    The forecaster currently emits a single point per call. Until
    multi-horizon GBM is trained, the orchestrator can synthesize a
    flat track at the single-point probability so `decide_trigger_time`
    has something to consume. The result is a degenerate "peak at t=0"
    track — which collapses to act_now, matching the pre-AC behaviour.
    """
    p = max(0.0, min(1.0, breach_probability))
    return [ForecastTrackPoint(minutes_ahead=h, breach_probability=p) for h in horizons_minutes]


__all__ = [
    "ACT_NOW_THRESHOLD_MINUTES",
    "DEFAULT_EFFECT_WINDOW_MINUTES",
    "ForecastTrackPoint",
    "TriggerDecision",
    "decide_trigger_time",
    "synthesize_flat_track",
]
