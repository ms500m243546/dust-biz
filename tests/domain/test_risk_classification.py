"""Phase AB — context-derived risk class tests."""

from __future__ import annotations

from datetime import UTC, datetime

from app.domain.risk_classification import (
    DEEP_BEHIND_RELATIVE_LOSS_THRESHOLD,
    DEEP_BEHIND_SLACK_THRESHOLD,
    END_OF_SHIFT_HOURS_REMAINING,
    END_OF_SHIFT_RELATIVE_LOSS_THRESHOLD,
    derive_risk_class,
)
from app.schemas.shift_progress import ShiftProgressSchema
from app.schemas.simulations import InterventionSimulationSchema


def _sim(*, tonnes: float) -> InterventionSimulationSchema:
    return InterventionSimulationSchema(
        simulation_id="SIM-x",
        requested_at=datetime(2026, 5, 3, 6, 0, tzinfo=UTC),
        intervention_id="x",
        target_zone_id="z",
        scenario="x",
        predicted_pm10_reduction=10.0,
        breach_probability_before=0.5,
        breach_probability_after=0.3,
        time_to_effect_minutes=5,
        production_loss_tonnes=tonnes,
        cycle_time_increase_percent=2.0,
        production_impact="medium",
        confidence=0.7,
        model_version="m",
        cost_model_version="c",
    )


def _progress(
    *, slack_ratio: float, hours_remaining: float
) -> ShiftProgressSchema:
    return ShiftProgressSchema(
        mine_id="m",
        shift_start=datetime(2026, 5, 3, 0, 0),
        now=datetime(2026, 5, 3, 12 - int(hours_remaining), 0),
        hours_elapsed=12.0 - hours_remaining,
        hours_remaining=hours_remaining,
        target_tonnes_per_hour=200.0,
        shift_target_tonnes=2400.0,
        tonnes_done=200.0 * (12 - hours_remaining) * slack_ratio,
        expected_done=200.0 * (12 - hours_remaining),
        slack_ratio=slack_ratio,
        source="synthetic",
    )


def test_no_progress_returns_base_unchanged() -> None:
    out = derive_risk_class(
        base_risk_class="medium",
        candidate=_sim(tonnes=500.0),
        shift_progress=None,
    )
    assert out.base == "medium"
    assert out.derived == "medium"
    assert out.reasons == ()


def test_on_plan_no_escalation() -> None:
    out = derive_risk_class(
        base_risk_class="medium",
        candidate=_sim(tonnes=500.0),
        shift_progress=_progress(slack_ratio=1.0, hours_remaining=6.0),
    )
    assert out.derived == "medium"
    assert out.reasons == ()


def test_deep_behind_plan_escalates_one_rank() -> None:
    # slack=0.5 < 0.7 AND tonnes/2400 = 0.125 > 0.10 → escalate
    out = derive_risk_class(
        base_risk_class="medium",
        candidate=_sim(tonnes=300.0),
        shift_progress=_progress(slack_ratio=0.5, hours_remaining=6.0),
    )
    assert out.base == "medium"
    assert out.derived == "high"
    assert any("behind plan" in r for r in out.reasons)


def test_end_of_shift_escalates_one_rank() -> None:
    # hours_remaining=1.0 < 1.5 AND tonnes/2400=0.0625 > 0.05 → escalate
    out = derive_risk_class(
        base_risk_class="low",
        candidate=_sim(tonnes=150.0),
        shift_progress=_progress(slack_ratio=1.0, hours_remaining=1.0),
    )
    assert out.derived == "medium"
    assert any("end-of-shift" in r for r in out.reasons)


def test_escalation_caps_at_high() -> None:
    # Both rules fire on a base=medium → cap at high (one-step + one-step
    # could double-escalate from low->medium->high, but from medium it
    # stops at high after one trigger anyway).
    out = derive_risk_class(
        base_risk_class="medium",
        candidate=_sim(tonnes=300.0),
        shift_progress=_progress(slack_ratio=0.4, hours_remaining=1.0),
    )
    assert out.derived == "high"
    # Both reasons present in the audit list.
    assert len(out.reasons) == 2


def test_low_base_can_double_escalate_to_high() -> None:
    # base=low, both rules fire: low -> medium (deep_behind) -> high (eos).
    out = derive_risk_class(
        base_risk_class="low",
        candidate=_sim(tonnes=300.0),
        shift_progress=_progress(slack_ratio=0.4, hours_remaining=1.0),
    )
    assert out.derived == "high"


def test_high_base_never_de_escalates() -> None:
    # Even when slack is huge and shift is fresh, a high base stays high.
    out = derive_risk_class(
        base_risk_class="high",
        candidate=_sim(tonnes=10.0),
        shift_progress=_progress(slack_ratio=2.5, hours_remaining=10.0),
    )
    assert out.derived == "high"
    assert out.reasons == ()


def test_unknown_base_class_normalises_to_low() -> None:
    out = derive_risk_class(
        base_risk_class="bogus",
        candidate=_sim(tonnes=10.0),
        shift_progress=_progress(slack_ratio=1.0, hours_remaining=6.0),
    )
    assert out.base == "low"
    assert out.derived == "low"


def test_thresholds_are_documented_constants() -> None:
    assert 0.0 < DEEP_BEHIND_SLACK_THRESHOLD <= 1.0
    assert 0.0 < DEEP_BEHIND_RELATIVE_LOSS_THRESHOLD <= 1.0
    assert END_OF_SHIFT_HOURS_REMAINING > 0.0
    assert 0.0 < END_OF_SHIFT_RELATIVE_LOSS_THRESHOLD <= 1.0
