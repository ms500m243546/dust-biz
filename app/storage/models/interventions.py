"""InterventionOption ORM (Phase G, S8).

Per docs/data-contracts.md `intervention_options`. Mutable catalog: an
operator may extend or tune the library at runtime, so the table
supports upsert. Reads from the recommendation engine (Phase H) and
the simulator (G.2) treat unknown intervention IDs as a hard error
per the S8 failure mode.
"""

from __future__ import annotations

from sqlalchemy import JSON, Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.storage.models.base import Base


class InterventionOption(Base):
    __tablename__ = "intervention_options"

    intervention_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    risk_class: Mapped[str] = mapped_column(String, nullable=False)
    requires_human_approval: Mapped[bool] = mapped_column(Boolean, nullable=False)
    automation_eligible_levels: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=False
    )
    estimated_time_to_effect_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    allowed_zone_types: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    # Phase Z — cause classes this intervention is designed to address.
    # Drawn from the zone-type vocabulary (haul_road, crusher, pit, etc.).
    # When the active source attribution names a zone whose type is in
    # this list, the optimizer adds `w_cause_match` to the candidate's
    # score. Empty list = no preference (no boost ever); legacy rows
    # without the column behave the same way.
    target_cause_classes: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=True
    )
    # Phase AD — shared resources this intervention consumes. Two
    # interventions across different zones that share a resource class
    # cannot fire concurrently (e.g. one water truck cannot service
    # two haul roads at once). The joint optimizer uses these to
    # break ties when multiple zones are at risk simultaneously.
    # Empty / NULL = no shared-resource constraint.
    resource_classes: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=True
    )
