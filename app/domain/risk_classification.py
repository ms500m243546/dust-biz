"""Context-derived risk classification (Phase AB, Tension 6).

The InterventionOption catalog ships with a `risk_class` (low / medium /
high) chosen at design time. Phase AB reinterprets that as a *floor*:
the same physical action can become more risky depending on the shift
context, and the ranker should reflect that without re-tuning the
catalog.

Derived class can ESCALATE the base, never DE-ESCALATE. A medium
catalog action under tight end-of-shift exposure becomes high; a high
action in slack midshift remains high. This is one-way.

Inputs surface from existing Phase AA shift_progress + the simulation:

  * `relative_loss` = tonnes_delayed / shift_target_tonnes (Phase AA)
  * `slack_ratio` (Phase AA)
  * `hours_remaining` (Phase AA)

The function is pure. The ranker calls it once per candidate; the
audit row records `base`, `derived`, and the human-readable reason
list so the supervisor can see *why* a familiar action escalated.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.optimization import RiskClassDerivation
from app.schemas.shift_progress import ShiftProgressSchema
from app.schemas.simulations import InterventionSimulationSchema

# Escalation thresholds. Tunable per-deployment via constants here
# (no operator-facing knob yet — first implementation stays
# conservative and audit-readable).
DEEP_BEHIND_SLACK_THRESHOLD = 0.7
DEEP_BEHIND_RELATIVE_LOSS_THRESHOLD = 0.10
END_OF_SHIFT_HOURS_REMAINING = 1.5
END_OF_SHIFT_RELATIVE_LOSS_THRESHOLD = 0.05

_RANKS: dict[str, int] = {"low": 0, "medium": 1, "high": 2}
_INVERSE: dict[int, str] = {0: "low", 1: "medium", 2: "high"}


@dataclass(frozen=True)
class DerivedRisk:
    """Result of a single derive_risk_class call.

    `base` is the catalog floor; `derived` is the post-escalation class
    the ranker should surface to the supervisor. `reasons` is the audit
    list (empty when no escalation fired).
    """

    base: str
    derived: str
    reasons: tuple[str, ...]

    def to_schema(self) -> RiskClassDerivation:
        return RiskClassDerivation(
            base=self.base,
            derived=self.derived,
            reasons=list(self.reasons),
        )


def derive_risk_class(
    *,
    base_risk_class: str,
    candidate: InterventionSimulationSchema,
    shift_progress: ShiftProgressSchema | None,
) -> DerivedRisk:
    """Derive the contextual risk class for one candidate.

    Returns the base class unchanged when no shift_progress is
    supplied — the rule is one-way and conservative; without the data
    we cannot honestly escalate, so we don't.
    """
    base = base_risk_class if base_risk_class in _RANKS else "low"
    if shift_progress is None or shift_progress.shift_target_tonnes <= 0.0:
        return DerivedRisk(base=base, derived=base, reasons=())

    relative_loss = (
        candidate.production_loss_tonnes / shift_progress.shift_target_tonnes
    )
    reasons: list[str] = []
    rank = _RANKS[base]

    deep_behind = (
        shift_progress.slack_ratio < DEEP_BEHIND_SLACK_THRESHOLD
        and relative_loss > DEEP_BEHIND_RELATIVE_LOSS_THRESHOLD
    )
    if deep_behind:
        rank = min(rank + 1, _RANKS["high"])
        reasons.append(
            f"behind plan (slack={shift_progress.slack_ratio:.2f}) and "
            f"relative loss {relative_loss:.1%} > "
            f"{DEEP_BEHIND_RELATIVE_LOSS_THRESHOLD:.0%}"
        )

    end_of_shift = (
        shift_progress.hours_remaining < END_OF_SHIFT_HOURS_REMAINING
        and relative_loss > END_OF_SHIFT_RELATIVE_LOSS_THRESHOLD
    )
    if end_of_shift:
        rank = min(rank + 1, _RANKS["high"])
        reasons.append(
            f"end-of-shift exposure ({shift_progress.hours_remaining:.1f}h "
            f"remaining) and relative loss {relative_loss:.1%} > "
            f"{END_OF_SHIFT_RELATIVE_LOSS_THRESHOLD:.0%}"
        )

    derived = _INVERSE[rank]
    return DerivedRisk(base=base, derived=derived, reasons=tuple(reasons))


__all__ = [
    "DEEP_BEHIND_RELATIVE_LOSS_THRESHOLD",
    "DEEP_BEHIND_SLACK_THRESHOLD",
    "END_OF_SHIFT_HOURS_REMAINING",
    "END_OF_SHIFT_RELATIVE_LOSS_THRESHOLD",
    "DerivedRisk",
    "derive_risk_class",
]
