"""Joint recommendation schemas (Phase BD.4).

Wire format for the multi-zone solver endpoint. The per-zone
recommendation logic is unchanged; the joint solver simply selects
non-conflicting interventions across zones using the catalog's
`resource_classes` discriminator.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.recommendations import RecommendationSchema


class JointSolveRequest(BaseModel):
    target_zone_ids: list[str] = Field(min_length=1, max_length=20)


class JointConflictSchema(BaseModel):
    """Audit row for a zone whose preferred candidate was demoted."""

    model_config = ConfigDict(from_attributes=True)

    zone_id: str
    preferred_intervention_id: str
    chosen_intervention_id: str
    conflicting_resource_classes: list[str] = Field(default_factory=list)
    conflicting_zone_id: str = ""


class JointSolveResponse(BaseModel):
    """Bundle of per-zone recommendations + conflict-resolution audit."""

    recommendations: list[RecommendationSchema] = Field(default_factory=list)
    conflicts: list[JointConflictSchema] = Field(default_factory=list)
    claimed_resources: dict[str, str] = Field(default_factory=dict)
    """Resource_class -> zone_id that won that resource."""
