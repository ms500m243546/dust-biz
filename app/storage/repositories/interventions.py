"""InterventionOption repository.

Reads + upsert. The library is small (tens of rows at most) and read-
mostly, so we don't bother with windowed queries.
"""

from __future__ import annotations

from sqlalchemy import select

from app.storage.models import InterventionOption
from app.storage.repositories.base import BaseRepository


class InterventionOptionRepository(BaseRepository):
    def get(self, intervention_id: str) -> InterventionOption | None:
        return self.session.get(InterventionOption, intervention_id)

    def list_all(self) -> list[InterventionOption]:
        stmt = select(InterventionOption).order_by(InterventionOption.intervention_id)
        return list(self.session.execute(stmt).scalars())

    def known_ids(self) -> set[str]:
        stmt = select(InterventionOption.intervention_id)
        return {row for row in self.session.execute(stmt).scalars()}

    def upsert(
        self,
        *,
        intervention_id: str,
        name: str,
        description: str,
        risk_class: str,
        requires_human_approval: bool,
        automation_eligible_levels: list[str],
        estimated_time_to_effect_minutes: int,
        allowed_zone_types: list[str],
        target_cause_classes: list[str] | None = None,
    ) -> InterventionOption:
        cause_classes = list(target_cause_classes or [])
        existing = self.session.get(InterventionOption, intervention_id)
        if existing is None:
            row = InterventionOption(
                intervention_id=intervention_id,
                name=name,
                description=description,
                risk_class=risk_class,
                requires_human_approval=requires_human_approval,
                automation_eligible_levels=list(automation_eligible_levels),
                estimated_time_to_effect_minutes=estimated_time_to_effect_minutes,
                allowed_zone_types=list(allowed_zone_types),
                target_cause_classes=cause_classes,
            )
            self.session.add(row)
        else:
            existing.name = name
            existing.description = description
            existing.risk_class = risk_class
            existing.requires_human_approval = requires_human_approval
            existing.automation_eligible_levels = list(automation_eligible_levels)
            existing.estimated_time_to_effect_minutes = estimated_time_to_effect_minutes
            existing.allowed_zone_types = list(allowed_zone_types)
            existing.target_cause_classes = cause_classes
            row = existing
        self.session.flush()
        return row
