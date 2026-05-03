"""Operator entry point for AP-42 intervention calibration (Phase R.2).

Usage:

    # Inspect calibration status against current ActionOutcome rows.
    python scripts/validate_intervention_calibration.py

    # Run the promotion check (without any side-effects on the
    # registry — set_current is a process-local call so this only
    # affects the current process).
    python scripts/validate_intervention_calibration.py --promote
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.domain.intervention_promotion import maybe_promote_ap42  # noqa: E402
from app.storage.database import session_scope  # noqa: E402
from app.training.intervention_validation import (  # noqa: E402
    validate_intervention_calibration,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--promote",
        action="store_true",
        help="Run maybe_promote_ap42() — flips the in-process registry only.",
    )
    args = parser.parse_args(argv)

    with session_scope() as session:
        report = validate_intervention_calibration(session)
    print(f"calibration status : {report.status}")
    print(f"joined rows        : {report.joined_row_count}")
    print(f"mean abs err pct   : {report.mean_abs_error_pct}")
    if report.sample_warning:
        print(f"warning            : {report.sample_warning}")
    if args.promote:
        promoted = maybe_promote_ap42()
        print(f"promotion          : {'ap42' if promoted else 'heuristic (held)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
