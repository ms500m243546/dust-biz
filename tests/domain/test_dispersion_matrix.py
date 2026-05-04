"""Phase BA.5 — DispersionMatrix reduction + persistence tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.domain.dispersion_matrix import (
    MissingResultsError,
    load_latest_for_mine,
    persist_dispersion_matrix,
    reduce_runs_to_matrix,
)
from app.schemas.dispersion import DispersionMatrixSchema, RegimeGridSchema
from app.storage.models import Mine


def _write_run(
    runs_dir: Path,
    regime_id: str,
    *,
    direction_deg: float,
    speed_ms: float,
    stability: str = "neutral",
    concentrations: dict[str, dict[str, float]] | None = None,
) -> None:
    rd = runs_dir / regime_id
    rd.mkdir(parents=True, exist_ok=True)
    (rd / "regime.json").write_text(
        json.dumps(
            {
                "regime_id": regime_id,
                "direction_deg": direction_deg,
                "speed_ms": speed_ms,
                "stability": stability,
            }
        )
    )
    (rd / "results.json").write_text(
        json.dumps(
            {
                "regime_id": regime_id,
                "concentrations": concentrations or {},
            }
        )
    )


def test_reduce_runs_to_matrix_assembles_grid_and_coefficients(
    tmp_path: Path,
) -> None:
    runs = tmp_path / "runs"
    _write_run(
        runs, "dir00_speed00_neutral",
        direction_deg=0.0, speed_ms=3.0,
        concentrations={"haul_road_W": {"cuncumen": 0.5, "caimanes": 0.1}},
    )
    _write_run(
        runs, "dir00_speed01_neutral",
        direction_deg=0.0, speed_ms=6.0,
        concentrations={"haul_road_W": {"cuncumen": 0.3, "caimanes": 0.2}},
    )
    matrix = reduce_runs_to_matrix(
        runs_dir=runs, mine_id="los-pelambres",
    )
    assert matrix.mine_id == "los-pelambres"
    assert matrix.regime_grid.directions_deg == [0.0]
    assert matrix.regime_grid.speeds_ms == [3.0, 6.0]
    assert matrix.regime_grid.stability_classes == ["neutral"]
    assert matrix.coefficients["dir00_speed00_neutral"]["haul_road_W"]["cuncumen"] == 0.5
    assert matrix.receptors() == ["caimanes", "cuncumen"]
    assert matrix.source_zones() == ["haul_road_W"]


def test_reduce_runs_to_matrix_skips_runs_without_results(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    # Good run.
    _write_run(
        runs, "dir00_speed00_neutral",
        direction_deg=0.0, speed_ms=3.0,
        concentrations={"x": {"r": 0.1}},
    )
    # Empty / failed regime — has regime.json but no results.json.
    bad = runs / "dir01_speed00_neutral"
    bad.mkdir(parents=True)
    (bad / "regime.json").write_text(
        json.dumps({"regime_id": "dir01_speed00_neutral", "direction_deg": 22.5, "speed_ms": 3.0})
    )
    matrix = reduce_runs_to_matrix(
        runs_dir=runs, mine_id="los-pelambres",
    )
    assert "dir00_speed00_neutral" in matrix.coefficients
    assert "dir01_speed00_neutral" not in matrix.coefficients


def test_reduce_runs_to_matrix_raises_when_no_results(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    runs.mkdir()
    with pytest.raises(MissingResultsError):
        reduce_runs_to_matrix(runs_dir=runs, mine_id="x")


def test_reduce_runs_to_matrix_raises_when_runs_dir_missing(tmp_path: Path) -> None:
    with pytest.raises(MissingResultsError):
        reduce_runs_to_matrix(runs_dir=tmp_path / "nope", mine_id="x")


def test_persist_and_reload_round_trip(session: Session) -> None:
    schema = DispersionMatrixSchema(
        mine_id="ba5-test-mine",
        model_version="dispersion_cfd_lookup_v0.1.0",
        regime_grid=RegimeGridSchema(
            directions_deg=[0.0, 90.0], speeds_ms=[3.0, 6.0]
        ),
        coefficients={
            "dir00_speed00_neutral": {"haul": {"recA": 0.4}},
            "dir01_speed00_neutral": {"haul": {"recA": 0.2}},
        },
    )
    session.add(
        Mine(mine_id="ba5-test-mine", name="BA5 test", default_automation_level="L1")
    )
    session.flush()
    persist_dispersion_matrix(session, schema)
    loaded = load_latest_for_mine(session, "ba5-test-mine")
    assert loaded is not None
    assert loaded.mine_id == "ba5-test-mine"
    assert loaded.coefficients["dir00_speed00_neutral"]["haul"]["recA"] == 0.4
    assert loaded.regime_grid.directions_deg == [0.0, 90.0]


def test_load_latest_for_mine_returns_none_when_absent(session: Session) -> None:
    out = load_latest_for_mine(session, "no-such-mine-ba5")
    assert out is None


def test_to_storage_dict_round_trip() -> None:
    schema = DispersionMatrixSchema(
        mine_id="x",
        model_version="v",
        regime_grid=RegimeGridSchema(directions_deg=[0.0]),
        coefficients={"r": {"s": {"t": 0.1}}},
        notes="hello",
    )
    d = schema.to_storage_dict()
    assert d["regime_grid"]["directions_deg"] == [0.0]
    assert d["coefficients"]["r"]["s"]["t"] == 0.1
    assert d["notes"] == "hello"
