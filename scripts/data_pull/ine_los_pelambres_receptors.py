"""Phase BB.7 — INE populated-places registry for Los Pelambres receptors.

Three of the six receptors in data_seed/los_pelambres.yaml ship with
TODO_FROM_RCA coordinates (lp-el-manzano, lp-chillepin, lp-coiron).
This script emits a hand-curated registry with best-effort coords
from open OSM + public commune records, flagged as `approximate`.

The authoritative source is INE's census shapefile export
(https://www.ine.cl/). This stub replaces the TODOs locally so the
BA campaign's receptor sampling boxes have real positions; the
operator should swap to INE-shipped coords before the deployment
audit gate runs (validate-rca-seed).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

# Best-effort approximations for the Los Pelambres receptor list.
# Sources: OSM `place=village` nodes + Chilean commune cadastres.
# Verify against INE census exports before shipping to production.
LOS_PELAMBRES_RECEPTORS: list[dict[str, object]] = [
    {
        "place_id": "lp-cuncumen",
        "name": "Cuncumén",
        "kind": "town",
        "longitude": -70.7010,
        "latitude": -31.9710,
        "population": 600,
        "coordinate_source": "rca_receptor_list",
    },
    {
        "place_id": "lp-caimanes",
        "name": "Caimanes",
        "kind": "town",
        "longitude": -71.1350,
        "latitude": -32.0200,
        "population": 1300,
        "coordinate_source": "rca_receptor_list",
    },
    {
        "place_id": "lp-salamanca",
        "name": "Salamanca",
        "kind": "town",
        "longitude": -70.9670,
        "latitude": -31.7780,
        "population": 25000,
        "coordinate_source": "rca_receptor_list",
    },
    {
        "place_id": "lp-el-manzano",
        "name": "El Manzano",
        "kind": "town",
        "longitude": -70.6200,
        "latitude": -31.8500,
        "population": 200,
        "coordinate_source": "approximate; verify via INE",
        "notes": "Salamanca commune; OSM place=village",
    },
    {
        "place_id": "lp-chillepin",
        "name": "Chillepín",
        "kind": "town",
        "longitude": -70.6500,
        "latitude": -31.9500,
        "population": 400,
        "coordinate_source": "approximate; verify via INE",
        "notes": "Choapa valley downstream of pit",
    },
    {
        "place_id": "lp-coiron",
        "name": "Coirón",
        "kind": "town",
        "longitude": -70.9100,
        "latitude": -31.8100,
        "population": 200,
        "coordinate_source": "approximate; verify via INE",
        "notes": "Salamanca commune",
    },
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out", default=str(ROOT / "data_cache" / "ine" / "los_pelambres_receptors.json"),
    )
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"places": LOS_PELAMBRES_RECEPTORS}, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote {len(LOS_PELAMBRES_RECEPTORS)} populated-place records -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
