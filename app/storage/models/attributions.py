"""SourceAttribution ORM (Phase F).

Per docs/data-contracts.md `source_attributions`. Append-only:
each attribution call lands a new row keyed on `dust_event_id` so
re-running attribution on the same event preserves history (a
later attribution may have better data than the first). The
"current" attribution for an event is whatever the latest
`issued_at` row says.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.storage.models.base import Base


def _default_labeled_at_from_issued(context: Any) -> datetime:
    issued_at: datetime = context.get_current_parameters()["issued_at"]
    return issued_at


class SourceAttribution(Base):
    __tablename__ = "source_attributions"

    attribution_id: Mapped[str] = mapped_column(String, primary_key=True)
    dust_event_id: Mapped[str] = mapped_column(
        ForeignKey("dust_events.event_id"), nullable=False, index=True
    )
    issued_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    affected_station: Mapped[str] = mapped_column(String, nullable=False)
    probable_sources: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    evidence_fields: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    model_version: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # M.2: anti-hindsight rules 3 + 4. Default `labeled_at = issued_at`
    # (context-aware). `derivation` distinguishes realtime model
    # output from post-event analysis (the latter is evaluation-only
    # and cannot be used as a training feature).
    labeled_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=_default_labeled_at_from_issued,
        index=True,
    )
    derivation: Mapped[str] = mapped_column(
        String, nullable=False, default="realtime_predicted", index=True
    )
    # M.3: causal-protocol rule 1. `evidence_class` describes the
    # *kind of evidence* supporting the attribution claim. Realistic
    # default for current single-station / observational data is
    # `observational_correlational`. Stronger classes (`quasi_experimental`,
    # `experimental`) require RCT-grade data we do not yet have.
    # `expert_judgment` for RCA-derived labels is evaluation-only.
    evidence_class: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="observational_correlational",
        index=True,
    )
