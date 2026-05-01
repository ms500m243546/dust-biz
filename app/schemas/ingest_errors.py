"""IngestError schema.

Surface form of the `ingest_errors` table for /api/v1/* endpoints
(introduced in Phase C.2). Append-only; no update path.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class IngestErrorSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    error_id: int | None = None
    received_at: datetime | None = None
    source_endpoint: str
    raw_payload: dict[str, Any]
    validation_errors: list[dict[str, Any]] = Field(default_factory=list)
    client_request_id: str | None = None
