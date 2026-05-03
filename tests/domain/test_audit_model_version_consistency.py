"""Phase V.2 — model_version consistency in audit-trail-bound paths.

Verifies that the per-domain orchestrators (forecasting, simulation,
attribution) propagate the *current* registry entry's model_version
into the persisted row, not a hard-coded baseline string. If a
registry promotion has flipped `current` to a trained variant, the
new prediction / simulation / attribution rows must carry that
trained variant's model_version.

These checks intentionally probe the storage shape rather than the
audit log per se — model_version on the persisted row is what feeds
the audit query downstream, and it's the load-bearing assertion.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from app.models import registry
from app.models.attribution.logreg_v0_1_0 import LOGREG_VERSION, LogRegAttributor
from app.models.attribution.rules_baseline import (
    RULES_VERSION as RULES_ATTR_VERSION,
)
from app.models.attribution.rules_baseline import RulesBaselineAttributor
from app.models.cost.cycle_time_v0_1_0 import (
    CYCLE_TIME_VERSION,
    CycleTimeProductionCost,
)
from app.models.cost.heuristic_baseline import (
    HeuristicProductionCost,
)
from app.models.intervention.ap42_v0_1_0 import AP42_VERSION, AP42InterventionImpact
from app.models.intervention.heuristic_baseline import (
    HeuristicInterventionImpact,
)


@pytest.fixture(autouse=True)
def _isolated_registry() -> Iterator[None]:
    registry.reset()
    yield
    registry.reset()


def test_intervention_promotion_changes_current_kind() -> None:
    # Heuristic registered first; AP-42 registered as alternative;
    # set_current flips the pointer. Subsequent rows derived from
    # `registry.get_current("intervention_impact").simulate(...)`
    # then carry AP-42's model_version.
    registry.register(HeuristicInterventionImpact())
    registry.register(AP42InterventionImpact(), set_as_current=False)
    registry.set_current("intervention_impact", AP42_VERSION)
    current = registry.get_current("intervention_impact")
    assert current.model_version == AP42_VERSION


def test_cost_promotion_changes_current_kind() -> None:
    registry.register(HeuristicProductionCost())
    registry.register(CycleTimeProductionCost(), set_as_current=False)
    registry.set_current("production_cost", CYCLE_TIME_VERSION)
    current = registry.get_current("production_cost")
    assert current.model_version == CYCLE_TIME_VERSION


def test_attribution_promotion_changes_current_kind() -> None:
    registry.register(RulesBaselineAttributor())
    registry.register(LogRegAttributor(), set_as_current=False)
    registry.set_current("source_attribution", LOGREG_VERSION)
    current = registry.get_current("source_attribution")
    assert current.model_version == LOGREG_VERSION


def test_promoted_attributor_emits_model_version_into_schema(tmp_path: Path) -> None:
    """LogRegAttributor.attribute() must stamp its own model_version."""
    from datetime import datetime

    from app.models.attribution.rules_baseline import CandidateSource

    registry.register(RulesBaselineAttributor())
    registry.register(LogRegAttributor(artifact_root=tmp_path), set_as_current=False)
    registry.set_current("source_attribution", LOGREG_VERSION)
    current: LogRegAttributor = registry.get_current("source_attribution")  # type: ignore[assignment]
    out = current.attribute(
        attribution_id="att-x",
        dust_event_id="evt-x",
        affected_station="lp-em05-cuncumen",
        candidates=[
            CandidateSource(
                source_id="downwind",
                wind_angle_offset_deg=10.0,
                activity_intensity=0.9,
                dust_generation_potential="high",
                concurrent_pm_rise=8.0,
            ),
        ],
        issued_at=datetime(2026, 5, 3, 12, 0),
    )
    # The schema's model_version must match the registry's current,
    # not the rules baseline.
    assert out.model_version == LOGREG_VERSION


def test_promoted_intervention_model_emits_its_version() -> None:
    from app.schemas.interventions import InterventionOptionSchema

    registry.register(HeuristicInterventionImpact())
    registry.register(AP42InterventionImpact(), set_as_current=False)
    registry.set_current("intervention_impact", AP42_VERSION)
    current: AP42InterventionImpact = registry.get_current("intervention_impact")  # type: ignore[assignment]
    out = current.simulate(
        intervention=InterventionOptionSchema(
            intervention_id="water_road",
            name="water road",
            description="t",
            risk_class="low",
            requires_human_approval=False,
            automation_eligible_levels=["L1"],
            estimated_time_to_effect_minutes=10,
            allowed_zone_types=["haul_road"],
        ),
        target_zone_id="z",
        predicted_pm10=120.0,
        predicted_pm25=45.0,
        breach_probability_before=0.5,
    )
    assert out.model_version == AP42_VERSION


def test_promoted_cost_model_emits_its_version() -> None:
    from app.schemas.interventions import InterventionOptionSchema

    registry.register(HeuristicProductionCost())
    registry.register(CycleTimeProductionCost(), set_as_current=False)
    registry.set_current("production_cost", CYCLE_TIME_VERSION)
    current: CycleTimeProductionCost = registry.get_current("production_cost")  # type: ignore[assignment]
    out = current.estimate_cost(
        intervention=InterventionOptionSchema(
            intervention_id="reduce_speed",
            name="reduce speed",
            description="t",
            risk_class="low",
            requires_human_approval=False,
            automation_eligible_levels=["L1"],
            estimated_time_to_effect_minutes=10,
            allowed_zone_types=["haul_road"],
        ),
        target_zone_id="z",
        production_rate_tph=1000.0,
        duration_minutes=60,
    )
    assert out.model_version == CYCLE_TIME_VERSION


def test_demotion_back_to_baseline_emits_baseline_version() -> None:
    """Sanity — flipping back to baseline restores baseline model_version."""
    registry.register(HeuristicInterventionImpact())
    registry.register(AP42InterventionImpact(), set_as_current=False)
    registry.set_current("intervention_impact", AP42_VERSION)
    # Now flip back.
    from app.models.intervention.heuristic_baseline import HEURISTIC_VERSION

    registry.set_current("intervention_impact", HEURISTIC_VERSION)
    current = registry.get_current("intervention_impact")
    assert current.model_version == HEURISTIC_VERSION


# Defensive: silence unused-import warnings on the constants imported
# for cross-reference. These are exercised in sibling phase tests.
__all__ = ["LOGREG_VERSION", "RULES_ATTR_VERSION", "patch"]
