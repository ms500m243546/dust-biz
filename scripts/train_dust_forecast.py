"""Operator entry point for dust-forecast model training (Phase P).

Usage (Phase P.1 skeleton):

    # Print the canonical Phase P.1 EvaluationProtocol hash without
    # running any training. Useful for pre-registration audit before
    # the first real fit (P.2).
    python scripts/train_dust_forecast.py --print-protocol

    # P.2: train + persist (will land in P.2; raises today).
    python scripts/train_dust_forecast.py \\
        --station lp-em05-cuncumen --horizon 60min

The script imports nothing API-side; pure domain + storage usage.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.training.dust_forecast_training import (  # noqa: E402
    DEFAULT_HORIZON,
    build_p1_protocol,
    train_one,
)
from app.schemas.forecasts import ForecastHorizon  # noqa: E402


# Phase P.1 default windows. Cuncumén has data from 2025-05-03 →
# 2026-05-03 (12 mo). Train: first 9 mo. Validation: next 1.5 mo.
# Test: last 1.5 mo (sealed). Embargo of 7 days between adjacent
# windows is asserted by the protocol validator.
DEFAULT_TRAIN_FROM = datetime(2025, 5, 3)
DEFAULT_TRAIN_TO = datetime(2026, 2, 3)
DEFAULT_VALIDATION_FROM = datetime(2026, 2, 10)
DEFAULT_VALIDATION_TO = datetime(2026, 3, 25)
DEFAULT_TEST_FROM = datetime(2026, 4, 1)
DEFAULT_TEST_TO = datetime(2026, 5, 3)


def _parse_date(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--station",
        default="lp-em05-cuncumen",
        help="Station sensor_id to train on (default: lp-em05-cuncumen).",
    )
    parser.add_argument(
        "--horizon",
        default=DEFAULT_HORIZON,
        choices=("15min", "30min", "60min", "120min", "24h"),
    )
    parser.add_argument("--train-from", type=_parse_date, default=DEFAULT_TRAIN_FROM)
    parser.add_argument("--train-to", type=_parse_date, default=DEFAULT_TRAIN_TO)
    parser.add_argument(
        "--validation-from", type=_parse_date, default=DEFAULT_VALIDATION_FROM
    )
    parser.add_argument(
        "--validation-to", type=_parse_date, default=DEFAULT_VALIDATION_TO
    )
    parser.add_argument("--test-from", type=_parse_date, default=DEFAULT_TEST_FROM)
    parser.add_argument("--test-to", type=_parse_date, default=DEFAULT_TEST_TO)
    parser.add_argument(
        "--print-protocol",
        action="store_true",
        help="Print the protocol hash + feature_set and exit (no fit).",
    )
    parser.add_argument(
        "--no-persist",
        action="store_true",
        help="Run the fit but skip artifact + metric_payload writes.",
    )
    args = parser.parse_args(argv)

    protocol = build_p1_protocol(
        train_window_from=args.train_from,
        train_window_to=args.train_to,
        validation_window_from=args.validation_from,
        validation_window_to=args.validation_to,
        test_window_from=args.test_from,
        test_window_to=args.test_to,
    )

    if args.print_protocol:
        print(f"protocol_version : {protocol.protocol_version}")
        print(f"protocol_hash    : {protocol.protocol_hash}")
        print(f"split_strategy   : {protocol.split_strategy}")
        print(f"feature_set      : {list(protocol.feature_set)}")
        print(f"max_ece          : {protocol.max_ece}")
        return 0

    horizon: ForecastHorizon = args.horizon  # type: ignore[assignment]
    try:
        result = train_one(
            station_id=args.station,
            horizon=horizon,
            protocol=protocol,
            persist=not args.no_persist,
        )
    except NotImplementedError as exc:
        print(f"train_one: {exc}", file=sys.stderr)
        return 2
    print(
        f"trained {result.model_version} for station={result.station_id} "
        f"horizon={result.horizon}: ece={result.ece} mae_pm10={result.mae_pm10} "
        f"breach_recall={result.breach_recall}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
