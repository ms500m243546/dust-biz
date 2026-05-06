"""Phase BA.4 — OpenFOAM campaign orchestrator.

Generates a regime grid (default 16 directions x 3 speeds = 48 runs),
copies the case template into per-regime run directories, patches the
placeholder boundary conditions / injection sites / receptor samplers,
and (in `--execute` mode) drives WSL to run `Allmesh` + `Allrun`.

In `--dry-run` mode (default), no OpenFOAM invocation happens — just
staging. CI exercises this path; the real campaign is operator-driven.

Inlet conditions follow Richards-Hoxey ABL:
    u_star  = U_ref * kappa / ln((z_ref + z_0) / z_0)
    k       = u_star^2 / sqrt(C_mu)
    epsilon = u_star^3 / (kappa * (z_ref + z_0))

with kappa = 0.4, z_0 = 0.05 m (mining/exposed-rock roughness),
C_mu = 0.09. z_ref = 10 m.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

KAPPA = 0.4
Z0 = 0.05
Z_REF = 10.0
C_MU = 0.09

DEFAULT_TEMPLATE_DIR = Path("cfd/los_pelambres/template")
DEFAULT_RUNS_DIR = Path("cfd/los_pelambres/runs")
DEFAULT_MINE_ID = "los-pelambres"

PLACEHOLDER_FILES: tuple[str, ...] = (
    "0/U",
    "0/k",
    "0/epsilon",
    "constant/cloudProperties",
    "system/topoSetDict",
)


@dataclass(frozen=True)
class Regime:
    """One row of the regime grid."""

    regime_id: str
    direction_deg: float  # meteorological "from" direction (0 = north)
    speed_ms: float
    stability: str  # "neutral" for the v0.1.0 campaign

    def inlet_vector(self) -> tuple[float, float, float]:
        """Return (Ux, Uy, Uz) for the inlet patch.

        Direction is "from" (meteorological); the wind vector points
        in the opposite direction. North = -y in the local frame
        established by dem_to_stl.py (y increases northward), so a
        wind FROM north blows TOWARD -y.
        """
        # "to" direction = from + 180 deg.
        to_rad = math.radians((self.direction_deg + 180.0) % 360.0)
        # Mathematical convention: 0 deg = +x (east), 90 deg = +y (north).
        # Met convention: 0 deg = north. Convert.
        # met_to_deg = 0 -> wind blowing towards south (y = -1)
        # met_to_deg = 90 -> blowing towards west (x = -1)
        # So Ux = -sin(met_to_rad) * speed, Uy = -cos(met_to_rad) * speed.
        # (The +180 already flipped to_rad above; reapply formula
        # consistently.)
        from_rad = math.radians(self.direction_deg)
        ux = -math.sin(from_rad) * self.speed_ms
        uy = -math.cos(from_rad) * self.speed_ms
        del to_rad  # documented but unused; we used `from_rad` directly
        return (ux, uy, 0.0)

    def inlet_turbulence(self) -> tuple[float, float]:
        """Return (k, epsilon) at z_ref via Richards-Hoxey ABL."""
        u_star = self.speed_ms * KAPPA / math.log((Z_REF + Z0) / Z0)
        k = (u_star * u_star) / math.sqrt(C_MU)
        eps = (u_star ** 3) / (KAPPA * (Z_REF + Z0))
        return k, eps


def parse_grid_spec(spec: str) -> tuple[int, int]:
    """`16x3` -> (16, 3); rejects non-positive parses."""
    try:
        a, b = spec.lower().split("x")
        n_dirs = int(a)
        n_speeds = int(b)
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"unrecognised --regime-grid {spec!r}; expected like 16x3") from exc
    if n_dirs < 1 or n_speeds < 1:
        raise ValueError(f"--regime-grid components must be >=1, got {spec!r}")
    return n_dirs, n_speeds


def speed_bins_from_climatology(
    climatology: dict[str, Any] | None,
    n_speeds: int,
) -> list[float]:
    """Pick `n_speeds` speed-bin centres from a climatology JSON.

    Climatology shape: {"percentiles": [{"p": 25, "speed_ms": 2.0}, ...]}.
    When None, fall back to evenly-spaced default bins covering the
    typical 2-10 m/s range observed at Los Pelambres in ERA5.
    """
    if climatology and "percentiles" in climatology:
        rows = climatology["percentiles"]
        # Pick bin centres at evenly-spaced percentiles spanning
        # 25..75 (by default) for n_speeds points.
        if n_speeds == 1:
            ps = [50]
        else:
            step = 50 / (n_speeds - 1)
            ps = [int(round(25 + step * i)) for i in range(n_speeds)]
        out = []
        for p in ps:
            best = min(rows, key=lambda r: abs(r["p"] - p))
            out.append(float(best["speed_ms"]))
        return out
    # Fallback grid: 3 m/s, 6 m/s, 9 m/s — covers Los Pelambres's
    # typical regime per ERA5 climatology over 2024-2025.
    if n_speeds == 1:
        return [6.0]
    if n_speeds == 2:
        return [4.0, 8.0]
    return [3.0, 6.0, 9.0][:n_speeds] + [
        3.0 + 3.0 * i for i in range(3, n_speeds)
    ]


def generate_regime_grid(
    *,
    n_dirs: int,
    n_speeds: int,
    climatology: dict[str, object] | None = None,
    stability: str = "neutral",
) -> list[Regime]:
    """Cartesian product of dirs x speeds, deterministic regime IDs."""
    speeds = speed_bins_from_climatology(climatology, n_speeds)
    out: list[Regime] = []
    for di in range(n_dirs):
        direction = (360.0 / n_dirs) * di
        for si, speed in enumerate(speeds):
            rid = f"dir{di:02d}_speed{si:02d}_{stability}"
            out.append(
                Regime(
                    regime_id=rid,
                    direction_deg=direction,
                    speed_ms=speed,
                    stability=stability,
                )
            )
    return out


def stage_run_dir(
    *,
    template_dir: Path,
    run_dir: Path,
    regime: Regime,
    injection_sites: str = "",
    receptor_samplers: str = "",
    receptor_cellzones: str = "",
) -> None:
    """Copy template to run_dir + patch all known placeholders in-place.

    `injection_sites` and `receptor_samplers` are pre-rendered OpenFOAM
    dictionary blocks the orchestrator (or operator) constructs from
    the mine's zone + receptor list. Empty strings are valid for a
    smoke run; the case will mesh and solve but produce no particle
    statistics.
    """
    # Idempotent overlay: copy template files in place. dirs_exist_ok
    # avoids the wipe-and-recreate path that races against AV /
    # OneDrive holding an open handle on terrain.stl. Stale files
    # written by a prior run for OTHER regimes are not re-written
    # here, but per-regime placeholder files (0/U etc.) ARE
    # overwritten below with regime-specific values.
    run_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(template_dir, run_dir, dirs_exist_ok=True)

    ux, uy, uz = regime.inlet_vector()
    k, eps = regime.inlet_turbulence()
    replacements: dict[str, str] = {
        "__INLET_UX__": f"{ux:.6f}",
        "__INLET_UY__": f"{uy:.6f}",
        "__INLET_UZ__": f"{uz:.6f}",
        "__INLET_K__": f"{k:.6e}",
        "__INLET_EPS__": f"{eps:.6e}",
        "__PARTICLE_INJECTION_SITES__": injection_sites,
        "__RECEPTOR_SAMPLERS__": receptor_samplers,
        "__RECEPTOR_CELLZONES__": receptor_cellzones,
    }
    for rel in PLACEHOLDER_FILES:
        path = run_dir / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for marker, value in replacements.items():
            text = text.replace(marker, value)
        path.write_text(text, encoding="utf-8")

    # Drop a regime.json beside the case for downstream tools.
    (run_dir / "regime.json").write_text(
        json.dumps(asdict(regime), indent=2), encoding="utf-8"
    )


def invoke_wsl_run(run_dir: Path, mesh: bool = True) -> int:
    """Drive WSL to run Allmesh + Allrun in `run_dir`.

    Translates the Windows path to its `/mnt/<drive>/...` WSL form.
    Returns the subprocess exit code; non-zero means OpenFOAM
    failed and the orchestrator should stop the campaign.
    """
    wsl_path = _windows_to_wsl_path(run_dir.resolve())
    cmds = []
    if mesh:
        cmds.append(f"cd {wsl_path} && ./Allmesh")
    cmds.append(f"cd {wsl_path} && ./Allrun")
    full = " && ".join(cmds)
    proc = subprocess.run(
        ["wsl.exe", "bash", "-lc", full],
        check=False,
    )
    return int(proc.returncode)


def _windows_to_wsl_path(path: Path) -> str:
    """`C:\\foo\\bar` -> `/mnt/c/foo/bar`. Pass-through on POSIX."""
    s = str(path)
    if len(s) >= 2 and s[1] == ":":
        drive = s[0].lower()
        rest = s[2:].replace("\\", "/")
        return f"/mnt/{drive}{rest}"
    return s.replace("\\", "/")


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="OpenFOAM campaign orchestrator (Phase BA.4)."
    )
    parser.add_argument(
        "--mine-id", default=DEFAULT_MINE_ID,
        help=f"Mine ID for run staging (default: {DEFAULT_MINE_ID}).",
    )
    parser.add_argument(
        "--template-dir", default=str(DEFAULT_TEMPLATE_DIR),
        help="OpenFOAM case template directory.",
    )
    parser.add_argument(
        "--runs-dir", default=str(DEFAULT_RUNS_DIR),
        help="Where staged run dirs land (gitignored).",
    )
    parser.add_argument(
        "--regime-grid", default="16x3",
        help="Grid spec, e.g. 16x3 or 8x2.",
    )
    parser.add_argument(
        "--climatology",
        help="Optional path to a climatology JSON with wind-speed percentiles.",
    )
    parser.add_argument(
        "--injection-sites",
        help="Path to a pre-rendered OpenFOAM injection-sites block.",
    )
    parser.add_argument(
        "--receptor-samplers",
        help="Path to a pre-rendered OpenFOAM receptor-samplers block.",
    )
    parser.add_argument(
        "--receptor-cellzones",
        help="Path to a pre-rendered topoSetDict cellzones block "
             "(replaces __RECEPTOR_CELLZONES__ in system/topoSetDict).",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run", action="store_true", default=True,
        help="Stage run dirs only; do not invoke OpenFOAM (default).",
    )
    mode.add_argument(
        "--execute", action="store_true", default=False,
        help="Stage AND invoke WSL/OpenFOAM per regime (operator-driven).",
    )
    parser.add_argument(
        "--mesh-once",
        action="store_true",
        default=False,
        help="In --execute mode, run Allmesh only on the first regime "
             "and reuse polyMesh across the others (BCs change, mesh doesn't).",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    n_dirs, n_speeds = parse_grid_spec(args.regime_grid)

    climatology: dict[str, object] | None = None
    if args.climatology:
        climatology = json.loads(Path(args.climatology).read_text(encoding="utf-8"))

    regimes = generate_regime_grid(
        n_dirs=n_dirs,
        n_speeds=n_speeds,
        climatology=climatology,
    )
    print(f"Generated {len(regimes)} regimes ({n_dirs} dirs x {n_speeds} speeds)")

    template_dir = Path(args.template_dir)
    runs_dir = Path(args.runs_dir)
    runs_dir.mkdir(parents=True, exist_ok=True)

    injection_sites = (
        Path(args.injection_sites).read_text(encoding="utf-8")
        if args.injection_sites
        else ""
    )
    receptor_samplers = (
        Path(args.receptor_samplers).read_text(encoding="utf-8")
        if args.receptor_samplers
        else ""
    )
    receptor_cellzones = (
        Path(args.receptor_cellzones).read_text(encoding="utf-8")
        if args.receptor_cellzones
        else ""
    )

    failed: list[str] = []
    for i, regime in enumerate(regimes):
        run_dir = runs_dir / regime.regime_id
        print(f"[{i+1}/{len(regimes)}] staging {regime.regime_id}")
        stage_run_dir(
            template_dir=template_dir,
            run_dir=run_dir,
            regime=regime,
            injection_sites=injection_sites,
            receptor_samplers=receptor_samplers,
            receptor_cellzones=receptor_cellzones,
        )
        if args.execute:
            mesh = (not args.mesh_once) or (i == 0)
            print(f"  -> WSL run (mesh={mesh})")
            rc = invoke_wsl_run(run_dir, mesh=mesh)
            if rc != 0:
                print(f"  ! regime {regime.regime_id} failed (rc={rc}); halting", file=sys.stderr)
                failed.append(regime.regime_id)
                break

    if failed:
        print(f"Campaign halted with failures: {failed}", file=sys.stderr)
        return 1
    print(f"Campaign {'staged' if args.dry_run and not args.execute else 'complete'}: {len(regimes)} regimes ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())
