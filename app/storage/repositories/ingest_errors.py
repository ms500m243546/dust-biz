"""IngestError repository.

Append-only error log for rejected ingestion payloads (G10).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.storage.models import IngestError
from app.storage.repositories.base import BaseRepository


class IngestErrorRepository(BaseRepository):
    def add(
        self,
        source_endpoint: str,
        raw_payload: dict[str, Any],
        validation_errors: list[dict[str, Any]],
        client_request_id: str | None = None,
    ) -> IngestError:
        err = IngestError(
            source_endpoint=source_endpoint,
            raw_payload=raw_payload,
            validation_errors=validation_errors,
            client_request_id=client_request_id,
        )
        self.session.add(err)
        self.session.flush()
        return err

    def recent(self, limit: int = 100) -> list[IngestError]:
        stmt = (
            select(IngestError)
            .order_by(IngestError.received_at.desc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars())

    def for_endpoint(self, source_endpoint: str, limit: int = 100) -> list[IngestError]:
        stmt = (
            select(IngestError)
            .where(IngestError.source_endpoint == source_endpoint)
            .order_by(IngestError.received_at.desc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars())
