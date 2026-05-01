"""Source attribution schemas (Phase F).

Per docs/data-contracts.md `source_attributions` and
docs/subsystem-contracts.md S7. The Attribution-named schema is
safety-relevant: the `validate-safety` scanner enforces the
presence of `confidence` (G2). Each ranked source carries its own
`confidence` and human-readable `reason`, satisfying the
guardrail-3 spirit at the per-source level.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProbableSource(BaseModel):
    """One ranked source candidate within a SourceAttribution."""

    source: str
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


class SourceAttributionSchema(BaseModel):
    """Wire format for an issued source attribution.

    `evidence_fields` carries supporting numbers (wind angle to
    source, time-lag correlation, recent activity intensity, etc.)
    so a reviewer can reconstruct why each source was ranked where
    it was. `model_version` and overall `confidence` per
    docs/model-contracts.md SourceAttributionModel return contract.
    """

    model_config = ConfigDict(from_attributes=True)

    attribution_id: str
    dust_event_id: str
    issued_at: datetime
    affected_station: str
    probable_sources: list[ProbableSource] = Field(default_factory=list)
    evidence_fields: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)
    model_version: str
