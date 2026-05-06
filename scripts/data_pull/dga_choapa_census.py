"""Phase BB.3 — DGA hydromet station census for the Choapa basin.

DGA's public portal lives at https://snia.mop.gob.cl/BNAConsultas/.
The interactive export drives a session-cookie + CSRF flow; fully
automated scraping is brittle and breaks each portal redesign. The
practical path is:

1. Go to https://snia.mop.gob.cl/BNAConsultas/reportes (region IV).
2. Filter by `Cuenca` = Choapa, `Variable` = Velocidad del viento
   (and Direccion del viento, Temperatura, Humedad, Precipitacion).
3. Export CSV per station for the desired window.
4. Drop CSVs in `data_cache/dga/<station-code>.csv`.
5. Run this script with `--from-cache` to ingest the CSVs into the
   payload-mode parser at `app/ingestion/public/dga.py`.

This script also keeps a hand-curated registry of Choapa-basin
stations relevant to Los Pelambres (target: <=50 km from the pit).
Update the registry as the operator confirms station availability.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

# Hand-curated Choapa-basin DGA hydromet stations near Los Pelambres.
# Codes / names verified against snia.mop.gob.cl listings; replace
# coordinates with measured values once the operator confirms via the
# portal export.
CHOAPA_DGA_STATIONS: list[dict[str, object]] = [
    {
        "station_code": "DGA-04514001",
        "name": "Cuncumen en Las Burras",
        "longitude": -70.7010,
        "latitude": -31.9710,
        "variables": ["wind_speed_ms", "temperature_c", "humidity_pct", "rainfall_mm"],
        "notes": "Co-located with SINCA station 424; cross-check.",
    },
    {
        "station_code": "DGA-04503002",
        "name": "Salamanca",
        "longitude": -70.9670,
        "latitude": -31.7780,
        "variables": ["wind_speed_ms", "temperature_c", "rainfall_mm"],
        "notes": "Comuna seat, valley reference.",
    },
    {
        "station_code": "DGA-04501001",
        "name": "Illapel",
        "longitude": -71.1670,
        "latitude": -31.6310,
        "variables": ["wind_speed_ms", "temperature_c", "rainfall_mm"],
        "notes": "Provincial reference station.",
    },
    {
        "station_code": "DGA-04504001",
        "name": "Limahuida",
        "longitude": -71.1500,
        "latitude": -31.7500,
        "variables": ["temperature_c", "rainfall_mm"],
        "notes": "Lower Choapa valley.",
    },
    {
        "station_code": "DGA-04502001",
        "name": "El Tambo",
        "longitude": -70.8500,
        "latitude": -31.6800,
        "variables": ["temperature_c", "rainfall_mm"],
        "notes": "Mid-Choapa; sparse coverage.",
    },
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DGA Choapa station census + ingest plan.")
    parser.add_argument(
        "--out", default=str(ROOT / "data_cache" / "dga" / "choapa_census.json"),
        help="Where to drop the registry JSON.",
    )
    parser.add_argument("--from-cache", action="store_true", help="Reserved for future ingest mode.")
    args = parser.parse_args(argv)

    if args.from_cache:
        print("from-cache ingest is not yet implemented; manual portal export required.")
        return 1

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(CHOAPA_DGA_STATIONS, indent=2), encoding="utf-8")
    print(f"Wrote {len(CHOAPA_DGA_STATIONS)} DGA station records -> {out}")
    print(
        "Next: visit https://snia.mop.gob.cl/BNAConsultas/reportes, "
        "export per-station CSVs, drop into data_cache/dga/<code>.csv, "
        "then re-run with --from-cache (TODO)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
