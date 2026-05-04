"""Phase Z — intervention_options.target_cause_classes column.

Adds the JSON column the Phase Z attribution-coupled ranker needs:

  intervention_options:
    + target_cause_classes  (JSON, NULL)

Nullable / default-NULL — legacy rows behave as "no cause preference"
under the Phase Z ranker (no boost ever). The schema layer coerces NULL
to [] so reads stay consistent.

Idempotent: ALTER TABLE ADD COLUMN is wrapped in a column-exists check.
Safe to re-run.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import inspect, text  # noqa: E402

from app.storage.database import get_engine, session_scope  # noqa: E402
from app.storage.models import Base  # noqa: E402

NEW_COLUMNS: list[tuple[str, str]] = [
    ("target_cause_classes", "JSON"),
]


def _column_exists(session, table: str, column: str) -> bool:
    rows = session.execute(text(f"PRAGMA table_info({table})")).all()
    return any(r[1] == column for r in rows)


def _add_columns(session) -> None:
    for name, sql_type in NEW_COLUMNS:
        if _column_exists(session, "intervention_options", name):
            continue
        session.execute(
            text(f"ALTER TABLE intervention_options ADD COLUMN {name} {sql_type}")
        )
        print(f"  + intervention_options.{name} ({sql_type}, NULL)")


def main() -> int:
    Base.metadata.create_all(get_engine())
    print("Z migration on dustops.db")
    with session_scope() as s:
        print("- intervention_options.target_cause_classes")
        _add_columns(s)
    insp = inspect(get_engine())
    existing = {c["name"] for c in insp.get_columns("intervention_options")}
    missing = [name for name, _ in NEW_COLUMNS if name not in existing]
    if missing:
        print(
            f"ERROR: post-migration columns missing on intervention_options: {missing}",
            file=sys.stderr,
        )
        return 1
    print("Z migration: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
