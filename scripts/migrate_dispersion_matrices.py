"""Phase BA.5 — dispersion_matrices table migration.

Creates the `dispersion_matrices` table on the dev SQLite DB if it
isn't there yet. Idempotent: re-runs are no-ops.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import inspect  # noqa: E402

from app.storage.database import get_engine  # noqa: E402
from app.storage.models import Base, DispersionMatrix  # noqa: E402


def main() -> int:
    engine = get_engine()
    print("BA.5 migration on dustops.db")
    Base.metadata.create_all(engine)
    insp = inspect(engine)
    if not insp.has_table(DispersionMatrix.__tablename__):
        print(
            f"ERROR: post-migration table missing: {DispersionMatrix.__tablename__}",
            file=sys.stderr,
        )
        return 1
    print(f"  + {DispersionMatrix.__tablename__} (mine_id, model_version, payload JSON, created_at)")
    print("BA.5 migration: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
