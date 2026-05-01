"""Mock data generator stub.

Placeholder. Real generators land in Phase C (Data Harness) per
PLAN.md. This file exists so the scaffold is complete and so future
sub-steps have a known landing spot.

Usage (Phase C onward):
    python scripts/seed_mock_data.py --mine demo --hours 6
"""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="DustOps AI mock data seeder")
    parser.add_argument(
        "--mine",
        default="demo",
        help="Mine ID to seed (default: demo)",
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=1,
        help="Hours of mock data to generate (default: 1)",
    )
    args = parser.parse_args()

    print(
        f"seed_mock_data: stub only. Phase C will generate {args.hours} h of "
        f"sensor/weather/equipment data for mine '{args.mine}'."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
