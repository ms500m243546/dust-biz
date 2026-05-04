"""DispersionMatrix reduction + persistence (Phase BA.5).

Walks a campaign runs directory, reads each regime's `results.json`
(written by the post-processing extraction step), and assembles a
`DispersionMatrixSchema` keyed by `regime_id` -> `source_zone_id` ->
`receptor_id` -> normalised concentration coefficient.

`results.json` is a thin extraction format the operator-side
extraction step writes after `Allrun` completes. Expected shape:

    {
      "regime_id": "dir00_speed00_neutral",
      "concentrations": {
        "<source_zone_id>": {
          "<receptor_id>": <normalised_concentration_float>,
          ...
        },
        ...
      }
    }

The orchestrator's actual extraction (parsing OpenFOAM
`postProcessing/cloudInfo/<time>/<receptor>.dat` files into this
shape) is operator-driven and ships in a follow-up. This module
consumes whatever JSON sits there.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from sqlalchemy.orm import Session

from app.schemas.dispersion import DispersionMatrixSchema, RegimeGridSchema
from app.storage.models import DispersionMatrix
from app.storage.repositories.dispersion import DispersionMatrixRepository

DEFAULT_MODEL_VERSION = "dispersion_cfd_lookup_v0.1.0"


class MissingResultsError(RuntimeError):
    """No `results.json` found in any of the campaign run directories."""


def _read_regime_results(run_dir: Path) -> dict[str, Any] | None:
    """Return the parsed `results.json` for one run, or None if missing."""
    path = run_dir / "results.json"
    if not path.exists():
        return None
    try:
        return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return None


def _read_regime_meta(run_dir: Path) -> dict[str, Any] | None:
    """Return the parsed `regime.json` for one run, or None if missing."""
    path = run_dir / "regime.json"
    if not path.exists():
        return None
    try:
        return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return None


def reduce_runs_to_matrix(
    *,
    runs_dir: Path,
    mine_id: str,
    model_version: str = DEFAULT_MODEL_VERSION,
    notes: str | None = None,
) -> DispersionMatrixSchema:
    """Walk `runs_dir`, gather results, return a DispersionMatrixSchema.

    Skips run directories without a `results.json` (failed or in-flight
    regimes); raises MissingResultsError when no run produced output.
    """
    if not runs_dir.exists() or not runs_dir.is_dir():
        raise MissingResultsError(f"runs_dir does not exist: {runs_dir}")

    coefficients: dict[str, dict[str, dict[str, float]]] = {}
    directions: set[float] = set()
    speeds: set[float] = set()
    stabilities: set[str] = set()

    for child in sorted(runs_dir.iterdir()):
        if not child.is_dir():
            continue
        results = _read_regime_results(child)
        if results is None:
            continue
        regime_id = results.get("regime_id") or child.name
        concentrations = results.get("concentrations") or {}
        if not isinstance(concentrations, dict):
            continue
        coefficients[regime_id] = {
            str(src): {
                str(rec): float(val)
                for rec, val in (recs or {}).items()
                if isinstance(val, (int, float))
            }
            for src, recs in concentrations.items()
            if isinstance(recs, dict)
        }
        meta = _read_regime_meta(child)
        if isinstance(meta, dict):
            d = meta.get("direction_deg")
            s = meta.get("speed_ms")
            st = meta.get("stability")
            if isinstance(d, (int, float)):
                directions.add(float(d))
            if isinstance(s, (int, float)):
                speeds.add(float(s))
            if isinstance(st, str):
                stabilities.add(st)

    if not coefficients:
        raise MissingResultsError(
            f"no results.json files found under {runs_dir}; "
            "campaign may not have completed"
        )

    grid = RegimeGridSchema(
        directions_deg=sorted(directions),
        speeds_ms=sorted(speeds),
        stability_classes=sorted(stabilities) or ["neutral"],
    )
    return DispersionMatrixSchema(
        mine_id=mine_id,
        model_version=model_version,
        regime_grid=grid,
        coefficients=coefficients,
        source_run_dir=str(runs_dir),
        notes=notes,
    )


def persist_dispersion_matrix(
    session: Session,
    schema: DispersionMatrixSchema,
) -> DispersionMatrix:
    """Append-only insert."""
    repo = DispersionMatrixRepository(session)
    row = DispersionMatrix(
        mine_id=schema.mine_id,
        model_version=schema.model_version,
        payload=schema.to_storage_dict(),
        created_at=datetime.now(UTC).replace(tzinfo=None),
    )
    return repo.add(row)


def load_latest_for_mine(
    session: Session, mine_id: str
) -> DispersionMatrixSchema | None:
    """Return the latest persisted schema for a mine, or None."""
    repo = DispersionMatrixRepository(session)
    row = repo.latest_for_mine(mine_id)
    if row is None:
        return None
    payload = row.payload or {}
    grid = payload.get("regime_grid") or {}
    return DispersionMatrixSchema(
        matrix_id=str(row.matrix_id),
        mine_id=row.mine_id,
        model_version=row.model_version,
        regime_grid=RegimeGridSchema(**grid) if isinstance(grid, dict) else RegimeGridSchema(),
        coefficients=payload.get("coefficients") or {},
        source_run_dir=payload.get("source_run_dir"),
        notes=payload.get("notes"),
        created_at=row.created_at,
    )


__all__ = [
    "DEFAULT_MODEL_VERSION",
    "MissingResultsError",
    "load_latest_for_mine",
    "persist_dispersion_matrix",
    "reduce_runs_to_matrix",
]
