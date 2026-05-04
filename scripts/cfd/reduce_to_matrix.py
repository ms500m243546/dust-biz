"""Phase BA.5 — CLI: reduce a runs/ directory to a DispersionMatrix.

Walks the campaign output, builds a `DispersionMatrixSchema`, persists
it via the API session, and writes a JSON artifact for inspection.
The lifespan hook (BA.10) picks up the persisted row at the next
FastAPI startup and promotes `cfd_lookup_v0.1.0` over the baseline
when the matrix has non-empty coefficients.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.domain.dispersion_matrix import (  # noqa: E402
    DEFAULT_MODEL_VERSION,
    persist_dispersion_matrix,
    reduce_runs_to_matrix,
)
from app.storage.database import session_scope  # noqa: E402


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reduce campaign runs to a DispersionMatrix."
    )
    parser.add_argument("--runs-dir", required=True, help="Path to cfd/<mine>/runs/")
    parser.add_argument("--mine-id", required=True)
    parser.add_argument("--out", help="Optional JSON dump path.")
    parser.add_argument(
        "--model-version", default=DEFAULT_MODEL_VERSION,
        help=f"Default: {DEFAULT_MODEL_VERSION}",
    )
    parser.add_argument("--notes", help="Free-form audit note.")
    parser.add_argument(
        "--no-persist",
        action="store_true",
        help="Skip DB write; only emit the JSON.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    runs_dir = Path(args.runs_dir)
    schema = reduce_runs_to_matrix(
        runs_dir=runs_dir,
        mine_id=args.mine_id,
        model_version=args.model_version,
        notes=args.notes,
    )
    print(
        f"Reduced {len(schema.coefficients)} regimes "
        f"({len(schema.source_zones())} sources x {len(schema.receptors())} receptors)"
    )

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(schema.model_dump(mode="json"), indent=2, default=str),
            encoding="utf-8",
        )
        print(f"  -> {out}")

    if not args.no_persist:
        with session_scope() as session:
            row = persist_dispersion_matrix(session, schema)
            print(f"Persisted matrix_id={row.matrix_id} for mine_id={args.mine_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
