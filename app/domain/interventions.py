"""Intervention library domain helpers (Phase G, S8).

Owns the default catalog shipped with the platform and the seeding
function that materializes it into the `intervention_options` table on
first read. Operators can override or extend any entry via the upsert
endpoint; the seed only fires when an `intervention_id` is missing,
never to overwrite a row an operator has tuned.

The defaults below are deliberately conservative on `risk_class` and
`automation_eligible_levels`. Per Guardrail 13 (`safety-guardrails.md`),
medium/high-risk actions cannot auto-execute even at L3, so those rows
ship with `automation_eligible_levels = []` and
`requires_human_approval = True`.
"""

from __future__ import annotations

from typing import TypedDict

from sqlalchemy.orm import Session

from app.schemas.interventions import InterventionOptionSchema
from app.storage.repositories.interventions import InterventionOptionRepository


class _CatalogEntry(TypedDict):
    intervention_id: str
    name: str
    description: str
    risk_class: str
    requires_human_approval: bool
    automation_eligible_levels: list[str]
    estimated_time_to_effect_minutes: int
    allowed_zone_types: list[str]
    target_cause_classes: list[str]
    resource_classes: list[str]


DEFAULT_INTERVENTIONS: list[_CatalogEntry] = [
    {
        "intervention_id": "increase_monitoring",
        "name": "Increase monitoring frequency",
        "description": (
            "Tighten polling on affected sensors and refresh forecasts at the "
            "shorter horizon. No operational change."
        ),
        "risk_class": "low",
        "requires_human_approval": False,
        "automation_eligible_levels": ["L3", "L4"],
        "estimated_time_to_effect_minutes": 0,
        "allowed_zone_types": [
            "pit",
            "haul_road",
            "stockpile",
            "dump",
            "crusher",
            "loading_area",
            "boundary",
        ],
        # Cause-agnostic monitoring action; receives no Phase Z boost
        # regardless of attribution. Empty target_cause_classes = neutral.
        "target_cause_classes": [],
        "resource_classes": [],
    },
    {
        "intervention_id": "raise_alert",
        "name": "Raise advisory alert",
        "description": (
            "Notify shift supervisor and environmental manager that risk is "
            "elevated; no operational change executed."
        ),
        "risk_class": "low",
        "requires_human_approval": False,
        "automation_eligible_levels": ["L3", "L4"],
        "estimated_time_to_effect_minutes": 0,
        "allowed_zone_types": [
            "pit",
            "haul_road",
            "stockpile",
            "dump",
            "crusher",
            "loading_area",
            "boundary",
        ],
        "target_cause_classes": [],
        "resource_classes": [],
    },
    {
        "intervention_id": "water_road",
        "name": "Water haul road segment",
        "description": (
            "Dispatch a water truck to the targeted haul road segment to "
            "suppress road dust generation for the next ~45 minutes."
        ),
        "risk_class": "medium",
        "requires_human_approval": True,
        "automation_eligible_levels": [],
        "estimated_time_to_effect_minutes": 10,
        "allowed_zone_types": ["haul_road"],
        "target_cause_classes": ["haul_road"],
        "resource_classes": ["water_truck_fleet"],
    },
    {
        "intervention_id": "reduce_speed",
        "name": "Reduce truck speed",
        "description": (
            "Temporarily reduce truck speed on selected haul road segment to "
            "cut road-dust entrainment."
        ),
        "risk_class": "medium",
        "requires_human_approval": True,
        "automation_eligible_levels": [],
        "estimated_time_to_effect_minutes": 10,
        "allowed_zone_types": ["haul_road"],
        "target_cause_classes": ["haul_road"],
        "resource_classes": [],
    },
    {
        "intervention_id": "reroute_trucks",
        "name": "Reroute trucks",
        "description": (
            "Divert a portion of truck flow from the affected haul road to an "
            "alternate route to reduce activity-driven dust at the boundary."
        ),
        "risk_class": "high",
        "requires_human_approval": True,
        "automation_eligible_levels": [],
        "estimated_time_to_effect_minutes": 20,
        "allowed_zone_types": ["haul_road"],
        "target_cause_classes": ["haul_road"],
        "resource_classes": ["dispatch_orchestration"],
    },
    {
        "intervention_id": "throttle_crusher",
        "name": "Throttle crusher throughput",
        "description": (
            "Reduce crusher throughput to lower fugitive dust at the crusher "
            "feed and discharge."
        ),
        "risk_class": "high",
        "requires_human_approval": True,
        "automation_eligible_levels": [],
        "estimated_time_to_effect_minutes": 15,
        "allowed_zone_types": ["crusher"],
        "target_cause_classes": ["crusher"],
        "resource_classes": ["primary_crusher"],
    },
    {
        "intervention_id": "pause_loading",
        "name": "Pause loading at zone",
        "description": (
            "Temporarily pause shovel loading in the affected pit/loading area "
            "until wind alignment improves."
        ),
        "risk_class": "high",
        "requires_human_approval": True,
        "automation_eligible_levels": [],
        "estimated_time_to_effect_minutes": 15,
        "allowed_zone_types": ["pit", "loading_area"],
        "target_cause_classes": ["pit", "loading_area"],
        "resource_classes": ["shovel_pool"],
    },
]


class UnknownInterventionError(LookupError):
    """Raised when a referenced intervention_id is not in the library."""


def seed_default_interventions(session: Session) -> int:
    """Insert any DEFAULT_INTERVENTIONS rows missing from the catalog.

    Returns the number of rows newly inserted. Existing rows are left
    untouched so operator tuning is preserved across restarts.
    """
    repo = InterventionOptionRepository(session)
    known = repo.known_ids()
    inserted = 0
    for entry in DEFAULT_INTERVENTIONS:
        if entry["intervention_id"] in known:
            continue
        repo.upsert(
            intervention_id=entry["intervention_id"],
            name=entry["name"],
            description=entry["description"],
            risk_class=entry["risk_class"],
            requires_human_approval=entry["requires_human_approval"],
            automation_eligible_levels=list(entry["automation_eligible_levels"]),
            estimated_time_to_effect_minutes=entry["estimated_time_to_effect_minutes"],
            allowed_zone_types=list(entry["allowed_zone_types"]),
            target_cause_classes=list(entry["target_cause_classes"]),
            resource_classes=list(entry["resource_classes"]),
        )
        inserted += 1
    return inserted


def list_interventions(session: Session) -> list[InterventionOptionSchema]:
    """Return the full library, seeding defaults if the table is empty."""
    repo = InterventionOptionRepository(session)
    rows = repo.list_all()
    if not rows:
        seed_default_interventions(session)
        rows = repo.list_all()
    return [InterventionOptionSchema.model_validate(r) for r in rows]


def require_known(session: Session, intervention_ids: list[str]) -> None:
    """Raise UnknownInterventionError if any ID is absent from the catalog.

    Closes D2-R2 / D-R3 at the boundary: zone admin and site config
    refer to interventions by ID, and unknown IDs must surface as a 4xx
    rather than silently rotting until the recommendation engine runs.
    """
    if not intervention_ids:
        return
    repo = InterventionOptionRepository(session)
    known = repo.known_ids()
    if not known:
        seed_default_interventions(session)
        known = repo.known_ids()
    missing = [iid for iid in intervention_ids if iid not in known]
    if missing:
        raise UnknownInterventionError(
            f"unknown intervention_id(s): {sorted(set(missing))}"
        )


__all__ = [
    "DEFAULT_INTERVENTIONS",
    "UnknownInterventionError",
    "list_interventions",
    "require_known",
    "seed_default_interventions",
]
