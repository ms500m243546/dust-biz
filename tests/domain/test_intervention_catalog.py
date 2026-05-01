"""Catalog seeding + ID validation tests.

`seed_default_interventions` is idempotent and never overwrites operator
edits; `require_known` is the boundary check that closes D2-R2 by
catching unknown intervention IDs at the zone admin endpoint.
"""

import pytest
from sqlalchemy.orm import Session

from app.domain.interventions import (
    DEFAULT_INTERVENTIONS,
    UnknownInterventionError,
    list_interventions,
    require_known,
    seed_default_interventions,
)
from app.storage.repositories.interventions import InterventionOptionRepository


def test_seed_inserts_full_catalog_on_empty_db(session: Session) -> None:
    inserted = seed_default_interventions(session)
    assert inserted == len(DEFAULT_INTERVENTIONS)
    repo = InterventionOptionRepository(session)
    assert repo.known_ids() == {str(e["intervention_id"]) for e in DEFAULT_INTERVENTIONS}


def test_seed_is_idempotent(session: Session) -> None:
    seed_default_interventions(session)
    again = seed_default_interventions(session)
    assert again == 0


def test_seed_does_not_overwrite_operator_edits(session: Session) -> None:
    repo = InterventionOptionRepository(session)
    repo.upsert(
        intervention_id="reduce_speed",
        name="Reduce truck speed (tuned)",
        description="operator-tuned copy",
        risk_class="low",  # operator chose looser class
        requires_human_approval=True,
        automation_eligible_levels=[],
        estimated_time_to_effect_minutes=5,
        allowed_zone_types=["haul_road"],
    )
    seed_default_interventions(session)
    row = repo.get("reduce_speed")
    assert row is not None
    assert row.description == "operator-tuned copy"
    assert row.risk_class == "low"


def test_list_interventions_lazy_seeds_when_empty(session: Session) -> None:
    out = list_interventions(session)
    assert len(out) == len(DEFAULT_INTERVENTIONS)


def test_require_known_seeds_then_raises_on_unknown(session: Session) -> None:
    with pytest.raises(UnknownInterventionError) as exc:
        require_known(session, ["reduce_speed", "summon_rain"])
    assert "summon_rain" in str(exc.value)


def test_require_known_passes_for_catalog_ids(session: Session) -> None:
    seed_default_interventions(session)
    require_known(session, ["reduce_speed", "water_road"])  # no raise


def test_require_known_noop_on_empty_input(session: Session) -> None:
    require_known(session, [])  # no raise; no seed required
    assert InterventionOptionRepository(session).known_ids() == set()


def test_default_catalog_safety_invariants() -> None:
    """Guardrails 13/14: medium/high risk cannot auto-execute."""
    for entry in DEFAULT_INTERVENTIONS:
        if entry["risk_class"] in ("medium", "high"):
            assert entry["automation_eligible_levels"] == [], entry["intervention_id"]
            assert entry["requires_human_approval"] is True, entry["intervention_id"]
