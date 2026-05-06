"""Phase BB.5 — Global Wind Atlas climatology export.

Global Wind Atlas (https://globalwindatlas.info/) hosts 250 m-resolution
wind climatology globally at multiple heights (10/50/100/200 m AGL).
The site's data is free under a CC-BY 4.0 license but the bulk-download
API is gated; the practical path is the public point-export tool.

Operator-manual steps:
1. Visit https://globalwindatlas.info/en/area/Chile/Coquimbo
   and zoom to Los Pelambres (~-31.73, -70.52).
2. Place a marker at the pit centroid; the right-hand panel exposes
   `Wind speed`, `Power density`, `Weibull A/k` per height.
3. Click "Generated PDF report" or "Generate GST file" to export.
4. Save the PDF/GST under data_cache/wind_atlas/los_pelambres_<height>m.{pdf,gst}.
5. Run this script with --extract to parse the GST into a percentile
   table consumable by scripts/cfd/run_campaign.py --climatology.

The lift over ERA5 climatology is real: GWA's mesoscale + microscale
chain captures terrain-driven wind regime detail at 250 m vs ERA5's
0.25 deg (~28 km) cell. For mine-scale dispersion campaigns this is
not optional once the pit recirculation matters.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def emit_climatology_template(out: Path) -> None:
    """Drop a placeholder climatology JSON the operator can replace.

    Shape matches what scripts/cfd/run_campaign.py reads: a list of
    {p, speed_ms} percentile rows. Default values come from coarse
    ERA5 climatology over Los Pelambres 2024-2025; replace once the
    GWA export lands.
    """
    payload = {
        "source": "ERA5 placeholder; replace with GWA point-export",
        "centroid": {"longitude": -70.5208, "latitude": -31.7300},
        "height_agl_m": 50,
        "percentiles": [
            {"p": 10, "speed_ms": 1.5},
            {"p": 25, "speed_ms": 2.8},
            {"p": 50, "speed_ms": 5.4},
            {"p": 75, "speed_ms": 8.2},
            {"p": 90, "speed_ms": 11.6},
        ],
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Global Wind Atlas climatology helper.",
    )
    parser.add_argument(
        "--emit-template",
        action="store_true",
        help="Emit an ERA5-derived climatology placeholder for run_campaign.",
    )
    parser.add_argument(
        "--out",
        default=str(
            ROOT / "data_cache" / "wind_atlas" / "los_pelambres_climatology.json"
        ),
    )
    args = parser.parse_args(argv)

    out = Path(args.out)
    if args.emit_template:
        emit_climatology_template(out)
        print(f"Wrote placeholder climatology -> {out}")
        return 0
    print(
        "Manual step: export point climatology from https://globalwindatlas.info/ "
        "for (-31.73, -70.52) at 50 m AGL and save to "
        f"{out.parent}.\nThen wire the parser (this script's --extract path) "
        "in a follow-up."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
