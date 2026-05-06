"""Phase BB.6 — SMA / SEIA filings scraper for Los Pelambres.

The SINCA portal is empty for 8 of 11 Los Pelambres receptors
(Caimanes, Coiron, Camisas, Hotel Mina, Quelen Alto, Chacay, Punta
Chungo, El Mauro). Their PM10 readings flow through SMA enforcement
filings and SEIA (https://seia.sea.gob.cl/) compliance reports
instead of the public real-time feed. Recovering even 2-3 of these
into the dev DB lifts BA.7 calibration from 1-receptor to 4-5-
receptor spatial diversity — the difference between "verifiable
dispersion matrix" and "Cuncumen-only fit".

The path is operator-manual + brittle:

1. Visit https://seia.sea.gob.cl/ and search:
   `Titular: Antofagasta Minerals` + `Region: Coquimbo` +
   `Tipo: Reportes Consolidados / Seguimiento Ambiental`.
2. Filter to Los Pelambres expediente IDs (RCAs 38/1997 + 050/2004
   amendments).
3. Download `Informe Consolidado de Seguimiento Ambiental` PDFs
   (typically quarterly). 2018-2025 should be available.
4. Save under data_cache/sma_seia/<expediente>/<period>.pdf.
5. Run this script with `--parse` to extract the PM10 tables (uses
   `pdfplumber`; install via `.venv\\Scripts\\pip install pdfplumber`).
6. The parser writes one CSV per (station, period) under
   data_cache/sma_seia/parsed/.
7. Run a future `seed_public_data.py --source sma_seia --from-cache`
   to load into the dev DB as `RawSensorReading` rows tagged
   `source = "sma_seia"` (joins the existing SINCA timeseries).

This script ships only the registry + the manual-flow doc. The PDF
parser path is wired but `--parse` raises NotImplementedError until
real PDFs land in the cache (their layout varies by year).

Recovered receptors lift BA.7 multi-receptor calibration -- the
critical gap noted in HANDOFF.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

# Receptor sensor-IDs in data_seed/los_pelambres.yaml that show
# `sinca_data_status: no_published_data`. Recovering ANY of these
# from SMA/SEIA closes part of the BA.7 multi-receptor gap.
EMPTY_SINCA_RECEPTORS: list[dict[str, object]] = [
    {"sensor_id": "lp-caimanes",       "rca": "RCA 050/2004 amendment"},
    {"sensor_id": "lp-coiron",         "rca": "RCA 38/1997"},
    {"sensor_id": "lp-camisas",        "rca": "RCA 38/1997"},
    {"sensor_id": "lp-hotel-mina",     "rca": "RCA 38/1997"},
    {"sensor_id": "lp-quelen-alto",    "rca": "RCA 38/1997"},
    {"sensor_id": "lp-chacay",         "rca": "RCA 050/2004"},
    {"sensor_id": "lp-punta-chungo",   "rca": "RCA 050/2004"},
    {"sensor_id": "lp-el-mauro",       "rca": "RCA 050/2004 amendment"},
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SMA/SEIA Los Pelambres receptor recovery.")
    parser.add_argument(
        "--out", default=str(ROOT / "data_cache" / "sma_seia" / "receptor_registry.json"),
    )
    parser.add_argument(
        "--parse", action="store_true",
        help="Parse PDFs already under data_cache/sma_seia/<expediente>/. "
             "Requires pdfplumber; ships TODO for now.",
    )
    args = parser.parse_args(argv)

    if args.parse:
        raise NotImplementedError(
            "PDF parsing path waits on real expediente layouts. The pdfplumber "
            "extractor lives at app/ingestion/public/sma_seia.py once authored."
        )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(EMPTY_SINCA_RECEPTORS, indent=2), encoding="utf-8")
    print(f"Wrote {len(EMPTY_SINCA_RECEPTORS)} receptor records -> {out}")
    print(
        "Operator follow-up: navigate https://seia.sea.gob.cl/ with "
        "Titular=Antofagasta Minerals + Region=Coquimbo, download "
        "Informe Consolidado de Seguimiento Ambiental PDFs, save under "
        "data_cache/sma_seia/<expediente>/<period>.pdf, then implement "
        "the --parse path."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
