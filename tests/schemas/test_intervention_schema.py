"""InterventionOption schema tests.

Field-level constraints the static safety scanner can't see (range,
non-empty IDs, allowed risk classes). G14 (`safety-guardrails.md`)
requires `requires_human_approval` and the automation-eligibility list
to be present; these are non-optional fields, so omitting them raises a
ValidationError.
"""

import pytest
from pydantic import ValidationError

from app.schemas.interventions import InterventionOptionSchema


def _payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "intervention_id": "reduce_speed",
        "name": "Reduce truck speed",
        "description": "Temporarily reduce truck speed on a haul road segment.",
        "risk_class": "medium",
        "requires_human_approval": True,
        "automation_eligible_levels": [],
        "estimated_time_to_effect_minutes": 10,
        "allowed_zone_types": ["haul_road"],
    }
    base.update(overrides)
    return base


def test_round_trip() -> None:
    s = InterventionOptionSchema(**_payload())  # type: ignore[arg-type]
    assert s.intervention_id == "reduce_speed"
    assert s.requires_human_approval is True
    assert s.automation_eligible_levels == []


def test_intervention_id_must_be_non_empty() -> None:
    with pytest.raises(ValidationError):
        InterventionOptionSchema(**_payload(intervention_id=""))  # type: ignore[arg-type]


def test_risk_class_must_be_known() -> None:
    with pytest.raises(ValidationError):
        InterventionOptionSchema(**_payload(risk_class="catastrophic"))  # type: ignore[arg-type]


def test_time_to_effect_must_be_non_negative() -> None:
    with pytest.raises(ValidationError):
        InterventionOptionSchema(**_payload(estimated_time_to_effect_minutes=-1))  # type: ignore[arg-type]


def test_zone_type_must_be_known() -> None:
    with pytest.raises(ValidationError):
        InterventionOptionSchema(**_payload(allowed_zone_types=["lunar_surface"]))  # type: ignore[arg-type]


def test_requires_human_approval_is_required() -> None:
    payload = _payload()
    payload.pop("requires_human_approval")
    with pytest.raises(ValidationError):
        InterventionOptionSchema(**payload)  # type: ignore[arg-type]
