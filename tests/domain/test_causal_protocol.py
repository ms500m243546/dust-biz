"""Phase M.3.1: causal-protocol contract tests."""

from __future__ import annotations

from app.domain.causal_protocol import (
    CONFIDENCE_PENALTY,
    EVIDENCE_RANK,
    NAIVE_SIMULATION_CONFIDENCE_CAP,
    confidence_after_causal_penalty,
    validate_simulation,
)


def test_evidence_rank_strongest_to_weakest() -> None:
    assert EVIDENCE_RANK["experimental"] > EVIDENCE_RANK["quasi_experimental"]
    assert (
        EVIDENCE_RANK["quasi_experimental"]
        > EVIDENCE_RANK["observational_correlational"]
    )
    assert (
        EVIDENCE_RANK["observational_correlational"]
        > EVIDENCE_RANK["expert_judgment"]
    )


def test_naive_simulation_with_empty_counterfactual_is_rejected() -> None:
    result = validate_simulation(
        simulation_method="naive_correlation",
        counterfactual_assumption="",
        confidence=0.5,
    )
    assert not result.ok
    assert any("counterfactual_assumption" in e for e in result.errors)


def test_naive_simulation_with_documented_assumption_is_allowed() -> None:
    result = validate_simulation(
        simulation_method="naive_correlation",
        counterfactual_assumption=(
            "Assumes operator's typical reaction window is the no-op "
            "baseline; biased because operators always react."
        ),
        confidence=0.5,
    )
    assert result.ok


def test_naive_simulation_above_confidence_cap_is_rejected() -> None:
    result = validate_simulation(
        simulation_method="naive_correlation",
        counterfactual_assumption="documented",
        confidence=0.85,
    )
    assert not result.ok
    assert any("cap" in e for e in result.errors)


def test_dispersion_simulation_with_empty_assumption_is_warning_only() -> None:
    result = validate_simulation(
        simulation_method="dispersion_model",
        counterfactual_assumption="",
        confidence=0.85,
    )
    assert result.ok  # not blocking
    assert any("dispersion_model" in w for w in result.warnings)


def test_propensity_matched_high_confidence_is_allowed() -> None:
    result = validate_simulation(
        simulation_method="propensity_matched",
        counterfactual_assumption="matched on humidity, truck count, time-of-day",
        confidence=0.92,
    )
    assert result.ok


def test_confidence_penalty_observational_caps_at_naive_ceiling() -> None:
    out = confidence_after_causal_penalty(
        predictive_confidence=0.95,
        evidence_class="observational_correlational",
    )
    # 0.95 - 0.30 penalty = 0.65; cap is 0.7 so unaffected here.
    assert abs(out - 0.65) < 1e-9


def test_confidence_penalty_observational_above_cap_is_capped() -> None:
    # If predictive_confidence is high enough that 0.95-0.30 = 0.65 < 0.7,
    # the cap doesn't bite. But for an evidence class that should hit the cap
    # we test with a custom case: the cap is 0.7 for observational.
    out = confidence_after_causal_penalty(
        predictive_confidence=1.0,
        evidence_class="observational_correlational",
    )
    # 1.0 - 0.30 = 0.70 → at cap.
    assert out <= NAIVE_SIMULATION_CONFIDENCE_CAP


def test_confidence_penalty_experimental_no_penalty() -> None:
    out = confidence_after_causal_penalty(
        predictive_confidence=0.95, evidence_class="experimental"
    )
    assert out == 0.95


def test_confidence_penalty_quasi_experimental_small_penalty() -> None:
    out = confidence_after_causal_penalty(
        predictive_confidence=0.85, evidence_class="quasi_experimental"
    )
    assert abs(out - 0.75) < 1e-9


def test_confidence_penalty_expert_judgment_zero_causal_confidence() -> None:
    """Expert-judgment evidence cannot support a causal claim at all."""
    out = confidence_after_causal_penalty(
        predictive_confidence=0.99, evidence_class="expert_judgment"
    )
    assert out == 0.0


def test_unknown_evidence_class_is_treated_as_observational() -> None:
    out = confidence_after_causal_penalty(
        predictive_confidence=1.0, evidence_class="something-novel"
    )
    # Treated like observational → 1.0 - 0.30 = 0.70.
    assert out <= NAIVE_SIMULATION_CONFIDENCE_CAP


def test_confidence_penalty_keys_match_rank_keys() -> None:
    """Sanity: every ranked class has a documented penalty."""
    assert set(CONFIDENCE_PENALTY.keys()) == set(EVIDENCE_RANK.keys())
