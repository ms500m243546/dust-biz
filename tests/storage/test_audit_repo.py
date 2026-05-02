"""AuditLog repository tests (Phase I)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.audit import record
from app.storage.repositories.audit import AuditLogRepository


def test_record_appends_row(session: Session) -> None:
    record(
        session,
        actor="alice",
        action="approve_recommendation",
        entity_type="recommendation",
        entity_id="REC-1",
        payload={"chosen_action_rank": 1},
        occurred_at=datetime(2026, 5, 1, 12, 0, 0),
    )
    session.commit()

    rows = AuditLogRepository(session).for_entity("recommendation", "REC-1")
    assert len(rows) == 1
    assert rows[0].action == "approve_recommendation"
    assert rows[0].payload == {"chosen_action_rank": 1}


def test_get_recent_filters_by_entity(session: Session) -> None:
    record(session, actor="a", action="x", entity_type="recommendation",
           entity_id="REC-1", occurred_at=datetime(2026, 5, 1, 1, 0))
    record(session, actor="a", action="x", entity_type="recommendation",
           entity_id="REC-2", occurred_at=datetime(2026, 5, 1, 2, 0))
    record(session, actor="a", action="x", entity_type="other",
           entity_id="X", occurred_at=datetime(2026, 5, 1, 3, 0))
    session.commit()

    repo = AuditLogRepository(session)
    rec_rows = repo.get_recent(
        since=datetime(2026, 5, 1, 0, 0), entity_type="recommendation"
    )
    assert {r.entity_id for r in rec_rows} == {"REC-1", "REC-2"}
