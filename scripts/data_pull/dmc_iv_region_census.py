"""Phase BB.4 — DMC (Dirección Meteorológica de Chile) IV Region station census.

DMC's public weather data lives at https://climatologia.meteochile.gob.cl/
and the API at https://api.meteochile.gob.cl/. The API requires a free
account + per-user API key; fully automated ingest waits for that.

Until then: hand-curate the IV Region stations relevant to Los Pelambres
and document the manual fetch + payload-mode ingest path.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

IV_REGION_DMC_STATIONS: list[dict[str, object]] = [
    {
        "station_code": "330020",
        "name": "La Serena Aerodromo",
        "longitude": -71.1992,
        "latitude": -29.9162,
        "altitude_m": 142,
        "notes": "Coastal reference; ~200 km north of Los Pelambres.",
    },
    {
        "station_code": "330021",
        "name": "Vicuna - Estacion Climatologica",
        "longitude": -70.7330,
        "latitude": -30.0330,
        "altitude_m": 730,
        "notes": "Inland Elqui valley; useful for andean wind regime.",
    },
    {
        "station_code": "330022",
        "name": "Ovalle - Granja",
        "longitude": -71.2000,
        "latitude": -30.5800,
        "altitude_m": 200,
        "notes": "Limari basin reference.",
    },
    {
        "station_code": "330023",
        "name": "Illapel",
        "longitude": -71.1700,
        "latitude": -31.6300,
        "altitude_m": 250,
        "notes": "Choapa province; closest DMC to Los Pelambres.",
    },
    {
        "station_code": "330024",
        "name": "Salamanca",
        "longitude": -70.9700,
        "latitude": -31.7800,
        "altitude_m": 580,
        "notes": "Comuna seat; cross-check with DGA Salamanca.",
    },
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DMC IV Region station census.")
    parser.add_argument(
        "--out", default=str(ROOT / "data_cache" / "dmc" / "iv_region_census.json"),
    )
    args = parser.parse_args(argv)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(IV_REGION_DMC_STATIONS, indent=2), encoding="utf-8")
    print(f"Wrote {len(IV_REGION_DMC_STATIONS)} DMC station records -> {out}")
    print(
        "Next: register at https://climatologia.meteochile.gob.cl/ for an "
        "API key, then build a fetch driver that hits "
        "/api/v1/datos/horarios for each station-code, normalises to the "
        "payload schema in app/ingestion/public/dmc.py, and writes "
        "data_cache/dmc/<station>.json."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
