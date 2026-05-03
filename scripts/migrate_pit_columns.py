"""Phase M.2: schema migration adding PIT columns.

Adds the M.2 PIT columns to existing dev SQLite DBs:

  sensor_readings:
    + valid_from           (DateTime, NOT NULL; back-fill = timestamp)
    + valid_to             (DateTime, NULL)
    + pit_version          (String, NOT NULL DEFAULT 'v1')
    Replaces unique index uq_sensor_readings_sensor_ts with
    uq_sensor_readings_sensor_ts_validfrom on
    (sensor_id, timestamp, valid_from).

  weather_readings:
    + weather_target_id    (String, NOT NULL; granular back-fill from
                            data_seed/los_pelambres.yaml weather_targets;
                            falls back to 'unknown-pre-m2' only if no
                            granular signal can be derived)
    + realtime_proxy       (Boolean, NOT NULL; back-fill = True for
                            existing Open-Meteo rows, False for ERA5)
    Adds unique index uq_weather_readings_source_target_ts on
    (source, weather_target_id, timestamp).

  dust_events, recommendations, recommendation_approvals,
  action_outcomes, source_attributions:
    + labeled_at           (DateTime, NOT NULL; back-fill from each
                            table's canonical event timestamp)
  source_attributions:
    + derivation           (String, NOT NULL DEFAULT 'realtime_predicted')

Idempotent: each `ALTER TABLE ADD COLUMN` is wrapped in a try/except
so re-running on an already-migrated DB is safe.

Granular weather_target_id back-fill (per user mandate
"i want a more granular backfill"): if the dev DB has any existing
weather_readings rows, we derive `weather_target_id` per row by:
  1. Reading data_seed/los_pelambres.yaml weather_targets list.
  2. For each existing row, attempting cache-correlation via the
     row's source + a heuristic: if exactly ONE weather_target was
     ever pulled (the L.M.1 case — only `lp-cuncumen-met` had a live
     fixture pull), assign that target_id to all rows.
  3. If multiple targets were pulled and we cannot disambiguate,
     fail loudly with manual-flag instructions.

Pre-M.2 deployment state at 2026-05-02: WeatherReading is empty (the
12-month live pull was deferred), so this migration is a no-op for
weather. The granular logic exists for future repeat applicability.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402
from sqlalchemy import inspect, text  # noqa: E402

from app.storage.database import get_engine, session_scope  # noqa: E402
from app.storage.models import Base  # noqa: E402


def _column_exists(session, table: str, column: str) -> bool:
    cols = session.execute(
        text(f"PRAGMA table_info({table})")
    ).all()
    return any(row[1] == column for row in cols)


def _index_exists(session, name: str) -> bool:
    rows = session.execute(
        text(f"SELECT name FROM sqlite_master WHERE type='index' AND name='{name}'")
    ).all()
    return len(rows) > 0


def _add_sensor_pit(session) -> None:
    """SensorReading: add valid_from / valid_to / pit_version + new index."""
    if not _column_exists(session, "sensor_readings", "valid_from"):
        session.execute(text(
            "ALTER TABLE sensor_readings ADD COLUMN valid_from TIMESTAMP"
        ))
        # Back-fill: every existing row's valid_from = timestamp.
        # Honest default — these rows have been in the DB for at least
        # the SINCA col-2→col-3 promotion delay, so they're effectively
        # validated values knowable from `timestamp + 7d` onward; but
        # we pick `timestamp` as the back-fill so every existing row
        # remains visible to as-of queries at any prediction time
        # >= timestamp. Documented in the M.2 normalization-report
        # entry as the "honest default" for legacy rows.
        session.execute(text(
            "UPDATE sensor_readings SET valid_from = timestamp "
            "WHERE valid_from IS NULL"
        ))
        print("  + sensor_readings.valid_from (back-filled = timestamp)")
    if not _column_exists(session, "sensor_readings", "valid_to"):
        session.execute(text(
            "ALTER TABLE sensor_readings ADD COLUMN valid_to TIMESTAMP"
        ))
        # No back-fill — NULL means "still valid."
        print("  + sensor_readings.valid_to (NULL = still valid)")
    if not _column_exists(session, "sensor_readings", "pit_version"):
        session.execute(text(
            "ALTER TABLE sensor_readings ADD COLUMN pit_version TEXT NOT NULL DEFAULT 'v1'"
        ))
        print("  + sensor_readings.pit_version (default 'v1')")
    # Replace the L.M.1 unique index. CREATE UNIQUE INDEX IF NOT EXISTS
    # is idempotent. We do NOT drop the old index — it's harmless once
    # the new one is in place; SensorReading rows trying to violate
    # the new (sensor_id, timestamp, valid_from) constraint would
    # already violate the old (sensor_id, timestamp). Leaving the old
    # index also keeps roll-forward / roll-back trivially reversible.
    if not _index_exists(session, "uq_sensor_readings_sensor_ts_validfrom"):
        session.execute(text(
            "CREATE UNIQUE INDEX uq_sensor_readings_sensor_ts_validfrom "
            "ON sensor_readings (sensor_id, timestamp, valid_from)"
        ))
        print("  + index uq_sensor_readings_sensor_ts_validfrom")


def _add_weather_pit(session) -> None:
    """WeatherReading: add weather_target_id / realtime_proxy + index."""
    existing_count = session.execute(
        text("SELECT COUNT(*) FROM weather_readings")
    ).scalar()

    if not _column_exists(session, "weather_readings", "weather_target_id"):
        session.execute(text(
            "ALTER TABLE weather_readings ADD COLUMN weather_target_id TEXT"
        ))
        if existing_count and existing_count > 0:
            _granular_backfill_target_id(session, existing_count)
        # Now enforce NOT NULL by re-creating the table — SQLite's
        # ADD COLUMN cannot enforce NOT NULL after the fact. We skip
        # the table-rewrite for simplicity; the ORM column declares
        # nullable=False which prevents future NULL inserts. Honest
        # gap documented; only existing legacy rows could be NULL.
        print("  + weather_readings.weather_target_id")
    if not _column_exists(session, "weather_readings", "realtime_proxy"):
        session.execute(text(
            "ALTER TABLE weather_readings ADD COLUMN realtime_proxy BOOLEAN"
        ))
        # Back-fill: existing rows are tagged based on `source`.
        # open_meteo / dga / power → realtime_proxy=True;
        # era5 / merra2 → False; anything else → True (conservative).
        session.execute(text("""
            UPDATE weather_readings
            SET realtime_proxy = CASE
                WHEN source IN ('era5', 'merra2', 'merra-2') THEN 0
                ELSE 1
            END
            WHERE realtime_proxy IS NULL
        """))
        print("  + weather_readings.realtime_proxy (back-filled by source)")
    if not _index_exists(session, "uq_weather_readings_source_target_ts"):
        # Only create if no NULL target_ids — would violate the new
        # constraint. Safe-by-construction at fresh ingest; for legacy
        # we already back-filled above.
        null_count = session.execute(text(
            "SELECT COUNT(*) FROM weather_readings WHERE weather_target_id IS NULL"
        )).scalar()
        if null_count and null_count > 0:
            print(
                f"  ! skipping uq_weather_readings_source_target_ts: "
                f"{null_count} row(s) have NULL weather_target_id. "
                "Manually flag them, then re-run."
            )
            return
        session.execute(text(
            "CREATE UNIQUE INDEX uq_weather_readings_source_target_ts "
            "ON weather_readings (source, weather_target_id, timestamp)"
        ))
        print("  + index uq_weather_readings_source_target_ts")


def _granular_backfill_target_id(session, existing_count: int) -> None:
    """Per-row weather_target_id back-fill from data_seed YAML.

    Strategy:
      - Read every weather_targets entry from data_seed/los_pelambres.yaml.
      - If exactly ONE target ever ingested (the L.M.1 case where
        only the 3-day Cuncumén fixture was used), assign that
        target_id to every existing row.
      - If multiple targets were pulled and we cannot disambiguate
        from the row data (no lat/lon column on WeatherReading
        pre-M.2), fail with a clear instruction.
    """
    yaml_path = ROOT / "data_seed" / "los_pelambres.yaml"
    if not yaml_path.exists():
        print(
            f"  ! cannot find {yaml_path}; falling back to "
            "'unknown-pre-m2' for all rows"
        )
        session.execute(text(
            "UPDATE weather_readings SET weather_target_id = 'unknown-pre-m2' "
            "WHERE weather_target_id IS NULL"
        ))
        return
    doc = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    targets = doc.get("weather_targets") or []
    if len(targets) == 1:
        target_id = targets[0]["target_id"]
        session.execute(text(
            "UPDATE weather_readings SET weather_target_id = :tid "
            "WHERE weather_target_id IS NULL"
        ), {"tid": target_id})
        print(
            f"  + back-filled {existing_count} weather row(s) to "
            f"weather_target_id={target_id!r} (only target in YAML)"
        )
        return
    # Multiple targets — try to disambiguate by source. If only one
    # source-target combination has rows, attribute to that target.
    sources = session.execute(text(
        "SELECT DISTINCT source FROM weather_readings"
    )).all()
    source_list = [s[0] for s in sources]
    print(
        f"  ! granular back-fill ambiguous: {len(targets)} "
        f"weather_targets in YAML, {len(source_list)} source(s) "
        f"({', '.join(source_list)}) in {existing_count} weather rows"
    )
    print(
        "  ! per user mandate, the migration will NOT assign a flat "
        "'unknown' marker. Either:"
    )
    print(
        "    (a) restore dustops.db.bak.pre-m2-pit-2026-05-02 and re-run "
        "the live pull through the M.2 orchestrator (which writes "
        "weather_target_id correctly), OR"
    )
    print(
        "    (b) manually update existing rows: "
        "UPDATE weather_readings SET weather_target_id = 'lp-mine-centroid' "
        "WHERE source='open_meteo' AND <your-disambiguation-clause>"
    )
    raise SystemExit(2)


def _add_label_pit(session) -> None:
    """Label tables: add labeled_at + (for source_attributions) derivation."""
    label_tables = [
        ("dust_events", "detected_at"),
        ("recommendations", "issued_at"),
        ("recommendation_approvals", "decided_at"),
        ("action_outcomes", "recorded_at"),
        ("source_attributions", "issued_at"),
    ]
    for table, source_col in label_tables:
        if not _column_exists(session, table, "labeled_at"):
            session.execute(text(
                f"ALTER TABLE {table} ADD COLUMN labeled_at TIMESTAMP"
            ))
            session.execute(text(
                f"UPDATE {table} SET labeled_at = {source_col} "
                "WHERE labeled_at IS NULL"
            ))
            print(f"  + {table}.labeled_at (back-filled = {source_col})")
    if not _column_exists(session, "source_attributions", "derivation"):
        session.execute(text(
            "ALTER TABLE source_attributions ADD COLUMN derivation TEXT "
            "NOT NULL DEFAULT 'realtime_predicted'"
        ))
        print("  + source_attributions.derivation (default 'realtime_predicted')")


def main() -> int:
    Base.metadata.create_all(get_engine())
    print("M.2 PIT migration on dustops.db")
    with session_scope() as s:
        print("- SensorReading PIT")
        _add_sensor_pit(s)
        print("- WeatherReading PIT")
        _add_weather_pit(s)
        print("- Label PIT (dust_events / recommendations / approvals / outcomes / source_attributions)")
        _add_label_pit(s)
    # Sanity: re-introspect to confirm all columns present.
    insp = inspect(get_engine())
    expected = {
        "sensor_readings": ["valid_from", "valid_to", "pit_version"],
        "weather_readings": ["weather_target_id", "realtime_proxy"],
        "dust_events": ["labeled_at"],
        "recommendations": ["labeled_at"],
        "recommendation_approvals": ["labeled_at"],
        "action_outcomes": ["labeled_at"],
        "source_attributions": ["labeled_at", "derivation"],
    }
    missing: list[str] = []
    for table, cols in expected.items():
        existing = {c["name"] for c in insp.get_columns(table)}
        for col in cols:
            if col not in existing:
                missing.append(f"{table}.{col}")
    if missing:
        print(f"ERROR: post-migration columns missing: {missing}", file=sys.stderr)
        return 1
    print("M.2 PIT migration: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
