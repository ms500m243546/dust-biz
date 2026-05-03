"""Phase M.3.1: causal-protocol schema migration.

Adds the M.3 causal-disclosure columns to existing dev SQLite DBs:

  source_attributions:
    + evidence_class       (String, NOT NULL DEFAULT 'observational_correlational')

  intervention_simulations:
    + simulation_method    (String, NOT NULL DEFAULT 'naive_correlation')
    + counterfactual_assumption (String, NOT NULL DEFAULT '')
    + selection_bias_caveat (Boolean, NOT NULL DEFAULT 1)

  recommendations:
    + causal_confidence    (Float, NOT NULL DEFAULT 0.5)

Idempotent. Re-running on an already-migrated DB is a no-op.

Honest defaults (per `docs/causal-protocol.md`): every legacy row gets
the *weakest* causal class — single-station observational data cannot
support stronger claims. Operators / future M.3.3 work upgrades the
class on a per-row basis when better evidence is available.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import inspect, text  # noqa: E402

from app.storage.database import get_engine, session_scope  # noqa: E402
from app.storage.models import Base  # noqa: E402


def _column_exists(session, table: str, column: str) -> bool:
    cols = session.execute(text(f"PRAGMA table_info({table})")).all()
    return any(row[1] == column for row in cols)


def main() -> int:
    Base.metadata.create_all(get_engine())
    print("M.3 causal-protocol migration on dustops.db")
    with session_scope() as s:
        # SourceAttribution.evidence_class
        if not _column_exists(s, "source_attributions", "evidence_class"):
            s.execute(text(
                "ALTER TABLE source_attributions ADD COLUMN evidence_class "
                "TEXT NOT NULL DEFAULT 'observational_correlational'"
            ))
            print("  + source_attributions.evidence_class")

        # InterventionSimulation columns
        if not _column_exists(s, "intervention_simulations", "simulation_method"):
            s.execute(text(
                "ALTER TABLE intervention_simulations ADD COLUMN simulation_method "
                "TEXT NOT NULL DEFAULT 'naive_correlation'"
            ))
            print("  + intervention_simulations.simulation_method")
        if not _column_exists(s, "intervention_simulations", "counterfactual_assumption"):
            s.execute(text(
                "ALTER TABLE intervention_simulations ADD COLUMN "
                "counterfactual_assumption TEXT NOT NULL DEFAULT ''"
            ))
            print("  + intervention_simulations.counterfactual_assumption")
        if not _column_exists(s, "intervention_simulations", "selection_bias_caveat"):
            s.execute(text(
                "ALTER TABLE intervention_simulations ADD COLUMN "
                "selection_bias_caveat BOOLEAN NOT NULL DEFAULT 1"
            ))
            print("  + intervention_simulations.selection_bias_caveat")

        # Recommendation.causal_confidence
        if not _column_exists(s, "recommendations", "causal_confidence"):
            s.execute(text(
                "ALTER TABLE recommendations ADD COLUMN causal_confidence "
                "REAL NOT NULL DEFAULT 0.5"
            ))
            print("  + recommendations.causal_confidence")

    insp = inspect(get_engine())
    expected = {
        "source_attributions": ["evidence_class"],
        "intervention_simulations": [
            "simulation_method",
            "counterfactual_assumption",
            "selection_bias_caveat",
        ],
        "recommendations": ["causal_confidence"],
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
    print("M.3 causal-protocol migration: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
