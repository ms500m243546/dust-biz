"""Causal protocol — programmatic enforcement of `docs/causal-protocol.md`.

Companion to `app/domain/evaluation_protocol.py`. Where evaluation_protocol
governs *temporal* discipline (no fitting to test set, no future leakage),
this module governs *counterfactual* discipline (no claiming causal
evidence we don't have).

What M.3.1 enforces:
- A `naive_correlation` `InterventionSimulation` with empty
  `counterfactual_assumption` is a hard error.
- An `observational_correlational` simulation with `confidence > 0.7` is
  a hard error (configurable cap per SiteConfiguration in future).
- An `EvaluationProtocol(causal_intent=True)` run whose training data
  contains only observational evidence is a hard error.

What M.3.1 does NOT do:
- Run propensity-score matching, IV regression, or any other causal
  inference. The realistic story for single-station observational data
  is "honest disclosure," not "manufactured causal evidence."
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

EvidenceClass = Literal[
    "experimental",
    "quasi_experimental",
    "observational_correlational",
    "expert_judgment",
]

SimulationMethod = Literal[
    "naive_correlation",
    "dispersion_model",
    "propensity_matched",
    "rct",
]

# Strongest → weakest. Used by `confidence_after_causal_penalty`.
EVIDENCE_RANK: dict[str, int] = {
    "experimental": 4,
    "quasi_experimental": 3,
    "observational_correlational": 2,
    "expert_judgment": 1,  # training-illegal anyway; ranked low
}

CONFIDENCE_PENALTY: dict[str, float] = {
    "experimental": 0.0,
    "quasi_experimental": 0.1,
    "observational_correlational": 0.3,
    "expert_judgment": 1.0,  # forces causal_confidence to 0
}

NAIVE_SIMULATION_CONFIDENCE_CAP = 0.7


class CausalViolation(Exception):
    """Raised when a causal-claim cannot be sustained by available evidence."""


@dataclass(frozen=True)
class CausalValidationResult:
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.errors


def confidence_after_causal_penalty(
    *,
    predictive_confidence: float,
    evidence_class: str,
) -> float:
    """Return causal_confidence given predictive_confidence + evidence_class.

    Caps at the naive-simulation ceiling of 0.7 for
    `observational_correlational` claims.
    """
    if evidence_class not in CONFIDENCE_PENALTY:
        # Conservative: unknown class treated as observational.
        evidence_class = "observational_correlational"
    penalty = CONFIDENCE_PENALTY[evidence_class]
    base = max(0.0, predictive_confidence - penalty)
    if evidence_class in ("observational_correlational", "expert_judgment"):
        return min(base, NAIVE_SIMULATION_CONFIDENCE_CAP)
    return base


def validate_simulation(
    *,
    simulation_method: str,
    counterfactual_assumption: str,
    confidence: float,
    naive_confidence_cap: float = NAIVE_SIMULATION_CONFIDENCE_CAP,
) -> CausalValidationResult:
    """Programmatic check of a single InterventionSimulation row.

    Errors at M.3.1:
      - simulation_method=naive_correlation with empty counterfactual
        assumption → hard error
      - confidence > naive_confidence_cap on a naive simulation → hard error
    """
    errors: list[str] = []
    warnings: list[str] = []

    if simulation_method == "naive_correlation":
        if not counterfactual_assumption.strip():
            errors.append(
                "naive_correlation simulation requires a non-empty "
                "counterfactual_assumption (per docs/causal-protocol.md S9). "
                "Document the world-model assumed — e.g., what the "
                "no-action baseline is and why it's biased."
            )
        if confidence > naive_confidence_cap:
            errors.append(
                f"naive_correlation simulation has confidence={confidence:.3f} "
                f"> cap {naive_confidence_cap:.2f}. Either lower confidence, "
                "use a stronger simulation_method, or override the cap "
                "via SiteConfiguration with explicit operator sign-off."
            )

    if simulation_method == "dispersion_model" and not counterfactual_assumption.strip():
        warnings.append(
            "dispersion_model simulation has empty counterfactual_assumption; "
            "consider documenting the dispersion engine + meteorology window "
            "for audit traceability."
        )

    return CausalValidationResult(
        errors=tuple(errors), warnings=tuple(warnings)
    )


def probe_causal_intent_training(
    session: Session,
    *,
    train_window_from: object,
    train_window_to: object,
) -> CausalValidationResult:
    """SQL probe for `EvaluationProtocol.causal_intent=True`.

    Anti-causal-overreach: a model claiming causal intent cannot have
    training data sourced entirely from `observational_correlational`
    attributions or `naive_correlation` simulations.
    """
    from sqlalchemy import func, select

    from app.storage.models import InterventionSimulation, SourceAttribution

    errors: list[str] = []
    warnings: list[str] = []

    # Probe 1: at least one stronger-than-observational attribution in window.
    stronger_attribution_count = session.execute(
        select(func.count())
        .select_from(SourceAttribution)
        .where(SourceAttribution.issued_at >= train_window_from)
        .where(SourceAttribution.issued_at <= train_window_to)
        .where(
            SourceAttribution.evidence_class.in_(
                ["experimental", "quasi_experimental"]
            )
        )
    ).scalar_one()

    total_attribution_count = session.execute(
        select(func.count())
        .select_from(SourceAttribution)
        .where(SourceAttribution.issued_at >= train_window_from)
        .where(SourceAttribution.issued_at <= train_window_to)
    ).scalar_one()

    if total_attribution_count and not stronger_attribution_count:
        errors.append(
            f"causal_intent=True but training window contains "
            f"{total_attribution_count} SourceAttribution row(s), all of "
            "which are observational_correlational or expert_judgment. "
            "Cannot sustain a causal claim from observational data alone "
            "(per docs/causal-protocol.md). Either: (a) drop "
            "causal_intent=True and recast as a predictive claim; "
            "(b) introduce quasi_experimental or experimental "
            "attributions before training."
        )

    # Probe 2: not all simulations are naive_correlation.
    sim_total = session.execute(
        select(func.count())
        .select_from(InterventionSimulation)
        .where(InterventionSimulation.requested_at >= train_window_from)
        .where(InterventionSimulation.requested_at <= train_window_to)
    ).scalar_one()
    sim_strong = session.execute(
        select(func.count())
        .select_from(InterventionSimulation)
        .where(InterventionSimulation.requested_at >= train_window_from)
        .where(InterventionSimulation.requested_at <= train_window_to)
        .where(
            InterventionSimulation.simulation_method.in_(
                ["dispersion_model", "propensity_matched", "rct"]
            )
        )
    ).scalar_one()

    if sim_total and not sim_strong:
        errors.append(
            f"causal_intent=True but training window contains "
            f"{sim_total} InterventionSimulation row(s), all of which "
            "use simulation_method=naive_correlation. Causal claims "
            "require at least one dispersion_model / propensity_matched "
            "/ rct simulation in the window."
        )

    return CausalValidationResult(
        errors=tuple(errors), warnings=tuple(warnings)
    )


__all__ = [
    "CONFIDENCE_PENALTY",
    "EVIDENCE_RANK",
    "NAIVE_SIMULATION_CONFIDENCE_CAP",
    "CausalValidationResult",
    "CausalViolation",
    "EvidenceClass",
    "SimulationMethod",
    "confidence_after_causal_penalty",
    "probe_causal_intent_training",
    "validate_simulation",
]
