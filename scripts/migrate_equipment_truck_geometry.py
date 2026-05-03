"""Phase O.1 — equipment truck-geometry columns.

Adds AP-42 unpaved-haul-road inputs to the existing dev SQLite DB:

  equipment:
    + empty_weight_tonnes    (Float, NULL)
    + tire_contact_area_m2   (Float, NULL)
    + tire_count             (Integer, NULL)
    + axle_count             (Integer, NULL)

All four columns are nullable — back-fill is a per-mine spec exercise
(manufacturer datasheets for the deployed fleet, or operator data once
the partnership lands). Legacy rows stay valid as NULL until then.

Idempotent: each ALTER TABLE ADD COLUMN is wrapped in a column-exists
check, so re-running on an already-migrated DB is safe.

See `docs/training-features.md` for the AP-42 formula and the mapping
of each column to the W = empty + payload term.
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
    ("empty_weight_tonnes", "REAL"),
    ("tire_contact_area_m2", "REAL"),
    ("tire_count", "INTEGER"),
    ("axle_count", "INTEGER"),
]


def _column_exists(session, table: str, column: str) -> bool:
    rows = session.execute(text(f"PRAGMA table_info({table})")).all()
    return any(r[1] == column for r in rows)


def _add_equipment_columns(session) -> None:
    for name, sql_type in NEW_COLUMNS:
        if _column_exists(session, "equipment", name):
            continue
        session.execute(text(
            f"ALTER TABLE equipment ADD COLUMN {name} {sql_type}"
        ))
        print(f"  + equipment.{name} ({sql_type}, NULL)")


def main() -> int:
    Base.metadata.create_all(get_engine())
    print("O.1 equipment truck-geometry migration on dustops.db")
    with session_scope() as s:
        print("- Equipment AP-42 columns")
        _add_equipment_columns(s)
    insp = inspect(get_engine())
    existing = {c["name"] for c in insp.get_columns("equipment")}
    missing = [name for name, _ in NEW_COLUMNS if name not in existing]
    if missing:
        print(f"ERROR: post-migration columns missing on equipment: {missing}", file=sys.stderr)
        return 1
    print("O.1 migration: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
