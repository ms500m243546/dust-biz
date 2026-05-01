"""S5 Feature pipeline schemas.

Per docs/data-contracts.md `features` (Phase E) and
docs/subsystem-contracts.md S5. The wire shape is intentionally
permissive: `feature_payload` is a namespaced JSON dict so the
heuristic baseline and any later trained model can declare their
own feature lists without a schema migration. The payload contract
itself is owned by the feature builder version
(`feature_pipeline_version`).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FeatureRecordSchema(BaseModel):
    """A single (timestamp, zone) feature row.

    The pipeline emits one of these per zone per compute pass.
    Persistence is via `FeatureRepository`; downstream models read
    the same schema (not the ORM directly).
    """

    model_config = ConfigDict(from_attributes=True)

    timestamp: datetime
    zone_id: str
    feature_pipeline_version: str
    feature_payload: dict[str, Any] = Field(default_factory=dict)
    missing_inputs: list[str] = Field(default_factory=list)
