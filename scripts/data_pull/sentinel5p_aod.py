"""Phase BB.8 — Sentinel-5P TROPOMI AOD cross-validation channel.

ESA Sentinel-5P (TROPOMI instrument) provides daily near-global aerosol
optical depth + UVAI products. Coarse spatial resolution (3.5 x 7 km)
but useful as a *second-opinion* channel post-BA.7 calibration: if the
dispersion matrix says receptor X sees high PM10 under regime Y, AOD
at receptor X should track. Disagreement is a calibration smell.

Access requires Copernicus Data Space Ecosystem auth
(https://dataspace.copernicus.eu/). Free with registration; bulk
downloads via openEO Python client (`pip install openeo`).

Operator-manual flow:

1. Register at https://dataspace.copernicus.eu/.
2. `pip install openeo` (heavyweight; do this in WSL or a separate venv
   to keep the production .venv clean).
3. Run a small openEO job to extract AOD time series at the Los
   Pelambres receptor coordinates over the 12-month sealed window.
4. Save as data_cache/sentinel5p/<receptor>/aod_timeseries.csv.
5. Build a comparison plot vs the dispersion-model predictions.

This script ships only the registry of receptor coords + the
documented flow. The actual extraction stays out-of-tree to keep CI
free of openeo + xarray + netCDF dependencies.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

# Receptor coordinates Sentinel-5P should sample. Driven from the same
# list as INE populated_places + SINCA receptor stations.
RECEPTOR_SAMPLES: list[dict[str, object]] = [
    {"id": "cuncumen",    "longitude": -70.7010, "latitude": -31.9710},
    {"id": "caimanes",    "longitude": -71.1350, "latitude": -32.0200},
    {"id": "salamanca",   "longitude": -70.9670, "latitude": -31.7780},
    {"id": "el_manzano",  "longitude": -70.6200, "latitude": -31.8500},
    {"id": "chillepin",   "longitude": -70.6500, "latitude": -31.9500},
    {"id": "coiron",      "longitude": -70.9100, "latitude": -31.8100},
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out", default=str(ROOT / "data_cache" / "sentinel5p" / "receptor_samples.json"),
    )
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(RECEPTOR_SAMPLES, indent=2), encoding="utf-8")
    print(f"Wrote {len(RECEPTOR_SAMPLES)} receptor sample points -> {out}")
    print(
        "Operator follow-up: register at dataspace.copernicus.eu, "
        "use openEO to extract AOD timeseries for these points "
        "over the BA.7 calibration window."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
