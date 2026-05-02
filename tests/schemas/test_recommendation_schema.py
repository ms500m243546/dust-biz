"""Recommendation schema tests.

The Recommendation-named classes are tracked by `validate-safety`
under the strictest pattern (G2 confidence + G3 reason + G15
model_version). These tests pin the field-level constraints the
scanner can't see.
"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.recommendations import (
    RecommendationActionSchema,
    RecommendationSchema,
)


def _action(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "rank": 1,
        "intervention_id": "water_road",
        "action": "Water Haul_Road_C",
        "breach_probability_after": 0.22,
        "production_loss": "low",
        "estimated_tonnes_delayed": 50.0,
        "confidence": 0.78,
        "reason": "Low production impact with sufficient PM10 reduction",
        "requires_human_approval": True,
        "risk_class": "medium",
        "simulation_id": "SIM-20260501-0001",
    }
    base.update(overrides)
    return base


def _payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "recommendation_id": "REC-20260501-00001",
        "issued_at": datetime(2026, 5, 1, 12, 5, tzinfo=UTC),
        "target_zone_id": "haul_c",
        "risk_event": "PM10 breach risk at haul_c",
        "current_breach_probability": 0.74,
        "target_probability": 0.25,
        "recommended_actions": [_action()],
        "requires_human_review": False,
        "compliance_priority_triggered": False,
        "confidence": 0.78,
        "reason": "Water Haul_Road_C now; expected breach drop 74% -> 22%",
        "model_version": "optimization_weighted_v0.1.0",
        "feature_pipeline_version": "features_v0.1.0",
        "input_data_quality_score": 0.9,
        "data_quality_warnings": [],
        "linked_prediction_ids": ["PRED-20260501-0001"],
        "linked_attribution_id": "ATTR-20260501-001",
        "automation_level": "L1",
        "top_production_impact": "low",
    }
    base.update(overrides)
    return base


def test_round_trip_carries_safety_fields() -> None:
    s = RecommendationSchema(**_payload())  # type: ignore[arg-type]
    # G2 + G3 + G15
    assert hasattr(s, "confidence")
    assert hasattr(s, "reason")
    assert hasattr(s, "model_version")
    assert s.linked_prediction_ids == ["PRED-20260501-0001"]


def test_action_round_trip_has_per_action_safety_fields() -> None:
    a = RecommendationActionSchema(**_action())  # type: ignore[arg-type]
    assert a.confidence > 0
    assert a.reason  # G3 at action level
    assert a.requires_human_approval is True  # G1


def test_overall_confidence_bounded() -> None:
    with pytest.raises(ValidationError):
        RecommendationSchema(**_payload(confidence=1.4))  # type: ignore[arg-type]


def test_target_probability_bounded() -> None:
    with pytest.raises(ValidationError):
        RecommendationSchema(**_payload(target_probability=-0.1))  # type: ignore[arg-type]


def test_action_rank_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        RecommendationActionSchema(**_action(rank=0))  # type: ignore[arg-type]


def test_production_loss_label_constrained() -> None:
    with pytest.raises(ValidationError):
        RecommendationActionSchema(**_action(production_loss="catastrophic"))  # type: ignore[arg-type]


def test_recommendation_with_no_actions_is_allowed() -> None:
    """G6 path: low-confidence + nothing safe to suggest -> empty list + review flag."""
    s = RecommendationSchema(
        **_payload(  # type: ignore[arg-type]
            recommended_actions=[],
            requires_human_review=True,
            confidence=0.3,
            reason="Confidence below threshold; monitor closely",
        )
    )
    assert s.recommended_actions == []
    assert s.requires_human_review is True
