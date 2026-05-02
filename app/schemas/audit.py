"""AuditLog schemas (Phase J deslop).

Wire format for `GET /api/v1/audit`. The dashboard reads from the
canonical `audit_logs` table (Phase I.2) instead of synthesizing
audit-shaped rows from `/approvals` + `/action-outcomes`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AuditLogSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    audit_id: int
    occurred_at: datetime
    actor: str
    action: str
    entity_type: str
    entity_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
