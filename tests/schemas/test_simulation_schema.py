"""Simulation schema tests.

The Simulation-named classes are tracked by the `validate-safety`
scanner (G2: `confidence` required); these tests pin the field-level
ranges and the joined-shape invariants the scanner can't see.
"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.simulations import (
    InterventionImpactSchema,
    InterventionSimulationSchema,
    ProductionCostEstimateSchema,
)


def _impact_payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "intervention_id": "reduce_speed",
        "target_zone_id": "haul_c",
        "predicted_pm10_reduction": 23.0,
        "predicted_pm25_reduction": 8.0,
        "breach_probability_before": 0.74,
        "breach_probability_after_action": 0.59,
        "time_to_effect_minutes": 10,
        "confidence": 0.7,
        "model_version": "intervention_impact_heuristic_v0.1.0",
        "source": "heuristic",
    }
    base.update(overrides)
    return base


def _cost_payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "intervention_id": "reduce_speed",
        "target_zone_id": "haul_c",
        "estimated_tonnes_delayed": 280.0,
        "cycle_time_increase_percent": 8.5,
        "bottleneck_risk": "medium",
        "production_impact": "medium",
        "confidence": 0.7,
        "model_version": "production_cost_heuristic_v0.1.0",
    }
    base.update(overrides)
    return base


def _sim_payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "simulation_id": "SIM-20260501-001",
        "requested_at": datetime(2026, 5, 1, 12, 5, tzinfo=UTC),
        "intervention_id": "reduce_speed",
        "target_zone_id": "haul_c",
        "scenario": "Reduce truck speed on haul_c",
        "predicted_pm10_reduction": 23.0,
        "predicted_pm25_reduction": 8.0,
        "breach_probability_before": 0.74,
        "breach_probability_after": 0.59,
        "time_to_effect_minutes": 10,
        "production_loss_tonnes": 280.0,
        "cycle_time_increase_percent": 8.5,
        "production_impact": "medium",
        "confidence": 0.7,
        "model_version": "intervention_impact_heuristic_v0.1.0",
        "cost_model_version": "production_cost_heuristic_v0.1.0",
        "source": "heuristic",
    }
    base.update(overrides)
    return base


def test_impact_round_trip_carries_safety_fields() -> None:
    s = InterventionImpactSchema(**_impact_payload())  # type: ignore[arg-type]
    assert s.confidence == 0.7
    assert s.model_version.startswith("intervention_impact_heuristic_")
    assert s.source == "heuristic"


def test_impact_breach_probability_bounded() -> None:
    with pytest.raises(ValidationError):
        InterventionImpactSchema(**_impact_payload(breach_probability_after_action=1.4))  # type: ignore[arg-type]


def test_impact_pm10_reduction_must_be_non_negative() -> None:
    with pytest.raises(ValidationError):
        InterventionImpactSchema(**_impact_payload(predicted_pm10_reduction=-1.0))  # type: ignore[arg-type]


def test_cost_round_trip() -> None:
    s = ProductionCostEstimateSchema(**_cost_payload())  # type: ignore[arg-type]
    assert s.production_impact == "medium"
    assert s.bottleneck_risk == "medium"


def test_simulation_round_trip_keeps_both_provenance_strings() -> None:
    s = InterventionSimulationSchema(**_sim_payload())  # type: ignore[arg-type]
    assert s.model_version.startswith("intervention_impact_heuristic_")
    assert s.cost_model_version.startswith("production_cost_heuristic_")
    assert s.confidence == 0.7
