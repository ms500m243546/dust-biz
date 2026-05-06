"""Phase BA.4 — campaign-orchestrator dry-run tests.

End-to-end staging of a synthetic case template without invoking
OpenFOAM. Verifies regime grid, ABL inlet derivation, placeholder
substitution, and WSL path translation.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from scripts.cfd.run_campaign import (
    C_MU,
    KAPPA,
    Z0,
    Z_REF,
    Regime,
    _windows_to_wsl_path,
    generate_regime_grid,
    parse_grid_spec,
    speed_bins_from_climatology,
    stage_run_dir,
)


def test_parse_grid_spec_canonical() -> None:
    assert parse_grid_spec("16x3") == (16, 3)
    assert parse_grid_spec("8X2") == (8, 2)


def test_parse_grid_spec_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        parse_grid_spec("16-3")
    with pytest.raises(ValueError):
        parse_grid_spec("0x3")


def test_generate_regime_grid_count() -> None:
    rg = generate_regime_grid(n_dirs=16, n_speeds=3)
    assert len(rg) == 48
    rg2 = generate_regime_grid(n_dirs=8, n_speeds=2)
    assert len(rg2) == 16
    # IDs must be unique.
    assert len({r.regime_id for r in rg}) == 48


def test_speed_bins_default_fallback() -> None:
    bins = speed_bins_from_climatology(None, 3)
    assert bins == [3.0, 6.0, 9.0]
    bins1 = speed_bins_from_climatology(None, 1)
    assert bins1 == [6.0]


def test_speed_bins_from_climatology() -> None:
    clim = {
        "percentiles": [
            {"p": 25, "speed_ms": 2.0},
            {"p": 50, "speed_ms": 5.0},
            {"p": 75, "speed_ms": 9.0},
        ]
    }
    bins = speed_bins_from_climatology(clim, 3)
    assert bins == [2.0, 5.0, 9.0]


def test_regime_inlet_vector_directions() -> None:
    # Wind FROM north (0 deg) blows TOWARD south (-y).
    r = Regime("t", direction_deg=0.0, speed_ms=10.0, stability="neutral")
    ux, uy, _ = r.inlet_vector()
    assert abs(ux) < 1e-6
    assert uy == pytest.approx(-10.0, abs=1e-6)
    # Wind FROM east (90 deg) blows TOWARD west (-x).
    r = Regime("t", direction_deg=90.0, speed_ms=10.0, stability="neutral")
    ux, uy, _ = r.inlet_vector()
    assert ux == pytest.approx(-10.0, abs=1e-6)
    assert abs(uy) < 1e-6


def test_regime_inlet_turbulence_richards_hoxey() -> None:
    r = Regime("t", direction_deg=0.0, speed_ms=8.0, stability="neutral")
    k, eps = r.inlet_turbulence()
    expected_u_star = 8.0 * KAPPA / math.log((Z_REF + Z0) / Z0)
    expected_k = (expected_u_star ** 2) / math.sqrt(C_MU)
    expected_eps = (expected_u_star ** 3) / (KAPPA * (Z_REF + Z0))
    assert k == pytest.approx(expected_k, rel=1e-6)
    assert eps == pytest.approx(expected_eps, rel=1e-6)


def test_stage_run_dir_replaces_placeholders(tmp_path: Path) -> None:
    template = tmp_path / "template"
    (template / "0").mkdir(parents=True)
    (template / "constant").mkdir()
    (template / "system").mkdir()
    (template / "0/U").write_text(
        "internalField uniform (__INLET_UX__ __INLET_UY__ __INLET_UZ__);"
    )
    (template / "0/k").write_text("internalField uniform __INLET_K__;")
    (template / "0/epsilon").write_text("internalField uniform __INLET_EPS__;")
    (template / "constant/cloudProperties").write_text(
        "// __PARTICLE_INJECTION_SITES__\n// __RECEPTOR_SAMPLERS__"
    )
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    regime = Regime("t", direction_deg=270.0, speed_ms=6.0, stability="neutral")
    stage_run_dir(
        template_dir=template,
        run_dir=runs_dir / regime.regime_id,
        regime=regime,
        injection_sites="// injection block",
        receptor_samplers="// receptor block",
    )
    u_text = (runs_dir / regime.regime_id / "0" / "U").read_text()
    assert "__INLET_UX__" not in u_text
    # Wind FROM west (270 deg) blows TOWARD east (+x): Ux > 0.
    assert "6.000000" in u_text
    cp_text = (runs_dir / regime.regime_id / "constant" / "cloudProperties").read_text()
    assert "// injection block" in cp_text
    assert "// receptor block" in cp_text
    regime_json = json.loads(
        (runs_dir / regime.regime_id / "regime.json").read_text()
    )
    assert regime_json["regime_id"] == "t"


def test_stage_run_dir_overlays_existing(tmp_path: Path) -> None:
    """Idempotency contract: re-running stage_run_dir on an existing
    run_dir must overlay template files (so placeholder values are
    re-patched) without wiping the directory. Stale per-regime files
    (e.g. a prior failed run's results.json) may persist; they don't
    interfere because placeholder-driven files are always re-written."""
    template = tmp_path / "template"
    template.mkdir()
    (template / "marker.txt").write_text("from_template")
    target = tmp_path / "runs" / "t"
    target.mkdir(parents=True)
    # Pre-existing stale file from a hypothetical prior run.
    (target / "stale.txt").write_text("prior_run")
    regime = Regime("t", direction_deg=0.0, speed_ms=5.0, stability="neutral")
    stage_run_dir(
        template_dir=template, run_dir=target, regime=regime,
    )
    # Template was overlaid.
    assert (target / "marker.txt").read_text() == "from_template"
    # Stale file persists — the overlay does NOT wipe. This is
    # intentional: avoids racing AV / OneDrive locks on freshly-
    # copied large files like terrain.stl.
    assert (target / "stale.txt").exists()


def test_stage_run_dir_re_patches_placeholders_on_rerun(tmp_path: Path) -> None:
    """Idempotency contract: a second run with a different regime
    overwrites the placeholder-driven files with the new regime's
    values. Without this, a re-run would silently keep stale BCs."""
    template = tmp_path / "template"
    (template / "0").mkdir(parents=True)
    (template / "0/U").write_text("uniform (__INLET_UX__ __INLET_UY__ __INLET_UZ__);")
    target = tmp_path / "runs" / "t"
    r1 = Regime("t", direction_deg=0.0, speed_ms=5.0, stability="neutral")
    stage_run_dir(template_dir=template, run_dir=target, regime=r1)
    first = (target / "0/U").read_text()

    r2 = Regime("t", direction_deg=180.0, speed_ms=8.0, stability="neutral")
    stage_run_dir(template_dir=template, run_dir=target, regime=r2)
    second = (target / "0/U").read_text()

    assert first != second
    # Wind FROM south (180): Ux=0, Uy positive (8 m/s northward).
    assert "8.000000" in second


def test_windows_to_wsl_path_drive_letter() -> None:
    assert _windows_to_wsl_path(Path(r"C:\Users\foo")) == "/mnt/c/Users/foo"
    assert _windows_to_wsl_path(Path(r"D:\runs\bar")) == "/mnt/d/runs/bar"


def test_windows_to_wsl_path_passthrough_posix() -> None:
    # Path("/foo/bar") on Windows still produces a leading-slash form
    # without a drive letter; should pass through unmangled.
    assert _windows_to_wsl_path(Path("/foo/bar")) == "/foo/bar"
