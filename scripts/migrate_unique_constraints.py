"""One-shot schema migration: add unique index to sensor_readings.

The repo manages schema with `Base.metadata.create_all` (no Alembic
yet — Phase B/E deliverable). `create_all` is additive: it will not
add a new constraint to an existing table. This script is the
in-repo migration we run by hand against any pre-L.M.1 dev DB to
add the `(sensor_id, timestamp)` unique index without dropping data.

Idempotent: uses `CREATE UNIQUE INDEX IF NOT EXISTS`. Re-running is
safe.

L.M.1 deferred the same migration for `weather_readings` because the
table needs a proper `weather_target_id` column first; that lands in
L.M.2.

Usage:

    python scripts/migrate_unique_constraints.py

Returns 0 on success, non-zero if the index could not be created (the
most common cause is residual duplicates — run the dedup SQL in the
L.M.1 handoff before retrying).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402

from app.storage.database import get_engine, session_scope  # noqa: E402
from app.storage.models import Base  # noqa: E402

_INDEX_NAME = "uq_sensor_readings_sensor_ts"
_CREATE_SQL = (
    f"CREATE UNIQUE INDEX IF NOT EXISTS {_INDEX_NAME} "
    "ON sensor_readings (sensor_id, timestamp)"
)


def main() -> int:
    Base.metadata.create_all(get_engine())
    with session_scope() as s:
        # Pre-flight: count duplicates so the operator sees them before
        # CREATE UNIQUE INDEX rejects.
        dup_check = s.execute(
            text(
                "SELECT COUNT(*) FROM ("
                "  SELECT sensor_id, timestamp FROM sensor_readings"
                "  GROUP BY sensor_id, timestamp HAVING COUNT(*) > 1"
                ")"
            )
        ).scalar()
        if dup_check:
            print(
                f"ERROR: {dup_check} (sensor_id, timestamp) pairs have "
                "duplicate rows. Run the dedup SQL in the L.M.1 handoff "
                "(or restore dustops.db.bak.pre-dedup-2026-05-02) before "
                "retrying.",
                file=sys.stderr,
            )
            return 1
        s.execute(text(_CREATE_SQL))
        print(f"created unique index {_INDEX_NAME} on sensor_readings(sensor_id, timestamp)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
