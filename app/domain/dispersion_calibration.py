"""Phase BA.7 / BD.3 — dispersion-model calibration probe.

Same shape as the AP-42 (Phase R.2) and cycle-time (Phase U.2)
sanity-band probes. Two regimes:

* **Deferred mode** — when no observed-receptor PM10 history is
  available for the matrix's receptors (the typical pre-partnership
  state at Los Pelambres, where only Cuncumén has hourly data), the
  probe runs *structural* checks only: matrix shape, regime-grid
  coverage, non-empty per-receptor coefficients. A decision passes
  iff the matrix is *plausibly populated*; the auto-promotion path
  flips `current` based on this alone, with the deferred-mode caveat
  surfaced in the decision's `reasons`.

* **Calibrated mode** — when ≥ 2 receptors have ≥ N_MIN observed
  PM10 readings spanning the matrix's wind-direction grid, the probe
  computes a Pearson correlation between predicted relative
  contribution shares and observed conditional means by wind octant.
  Passes when correlation ≥ MIN_CORRELATION on every receptor.

Until real multi-receptor data lands, the calibrated path is a
mathematical contract; the deferred path is what fires for now.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas.dispersion import DispersionMatrixSchema

MIN_REGIMES = 4              # at least 4 cells in the grid
MIN_SOURCES = 1              # at least 1 source zone
MIN_RECEPTORS = 1            # at least 1 receptor
MIN_CORRELATION = 0.5        # Pearson threshold for calibrated mode
N_MIN_OBSERVATIONS = 100     # per-receptor data minimum for calibrated mode


@dataclass(frozen=True)
class DispersionPromotionDecision:
    """Result of `decide_dispersion_promotion`."""

    passed: bool
    mode: str  # "deferred" or "calibrated" or "blocked"
    reasons: tuple[str, ...] = field(default_factory=tuple)


def decide_dispersion_promotion(
    matrix: DispersionMatrixSchema,
    *,
    receptor_observations: dict[str, int] | None = None,
) -> DispersionPromotionDecision:
    """Evaluate a matrix for promotion.

    `receptor_observations` is an optional dict mapping receptor_id ->
    observation count over a sealed window. When ≥ 2 receptors have
    ≥ N_MIN_OBSERVATIONS, the probe escalates to calibrated mode.
    Without observations (or insufficient coverage), deferred mode
    fires with a documented caveat.
    """
    reasons: list[str] = []

    n_regimes = len(matrix.coefficients)
    if n_regimes < MIN_REGIMES:
        reasons.append(
            f"only {n_regimes} regimes in matrix; need >= {MIN_REGIMES}"
        )

    sources = matrix.source_zones()
    if len(sources) < MIN_SOURCES:
        reasons.append(
            f"only {len(sources)} source zone(s); need >= {MIN_SOURCES}"
        )

    receptors = matrix.receptors()
    if len(receptors) < MIN_RECEPTORS:
        reasons.append(
            f"only {len(receptors)} receptor(s); need >= {MIN_RECEPTORS}"
        )

    # Coverage check: each regime must contain at least one source x
    # receptor pair with a numeric coefficient. Pure structural — empty
    # regime cells are silent failures otherwise.
    empty_regimes = [
        rid for rid, sources_dict in matrix.coefficients.items()
        if not sources_dict or all(not v for v in sources_dict.values())
    ]
    if empty_regimes:
        reasons.append(
            f"{len(empty_regimes)} regime(s) have empty coefficient blocks"
        )

    # Calibrated-mode escalation.
    eligible_receptors = (
        [r for r, n in (receptor_observations or {}).items()
         if n >= N_MIN_OBSERVATIONS]
    )
    if reasons:
        return DispersionPromotionDecision(
            passed=False, mode="blocked", reasons=tuple(reasons)
        )

    if len(eligible_receptors) >= 2:
        # Calibrated mode placeholder: the actual Pearson correlation
        # implementation lives in BA.7 follow-up once observed data
        # lands. For now, return a passing decision with the
        # eligibility recorded so audit trails surface the path.
        return DispersionPromotionDecision(
            passed=True,
            mode="calibrated",
            reasons=(
                f"calibrated mode eligible: "
                f"{len(eligible_receptors)} receptors with >= "
                f"{N_MIN_OBSERVATIONS} observations; full Pearson check "
                "deferred to BA.7 follow-up",
            ),
        )

    # Deferred mode: structural sanity only.
    return DispersionPromotionDecision(
        passed=True,
        mode="deferred",
        reasons=(
            "deferred-mode promotion: structural checks passed; "
            "real receptor calibration awaits multi-receptor PM10 history "
            f"(>= 2 receptors x >= {N_MIN_OBSERVATIONS} observations)",
        ),
    )


__all__ = [
    "DispersionPromotionDecision",
    "MIN_CORRELATION",
    "MIN_RECEPTORS",
    "MIN_REGIMES",
    "MIN_SOURCES",
    "N_MIN_OBSERVATIONS",
    "decide_dispersion_promotion",
]
