"""ingest_errors - append-only record of rejected ingestion payloads.

Honors safety guardrail G10 (`docs/safety-guardrails.md`): bad data
must not silently poison the model. Anything that fails schema
validation at the ingestion endpoints lands here for later
inspection rather than being dropped.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.storage.models.base import Base


class IngestError(Base):
    __tablename__ = "ingest_errors"

    error_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )
    source_endpoint: Mapped[str] = mapped_column(String, nullable=False, index=True)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    validation_errors: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    client_request_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
