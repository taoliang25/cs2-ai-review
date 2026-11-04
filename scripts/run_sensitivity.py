"""Run distance and early-window sensitivity checks on one fact database."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cs2_review.sensitivity import run_threshold_sensitivity  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check sensitivity of current behavior-rule thresholds."
    )
    parser.add_argument(
        "databases",
        nargs="+",
        type=Path,
        help="One or more imported SQLite fact databases",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "experiments" / "results",
    )
    args = parser.parse_args()

    try:
        responses = [
            run_threshold_sensitivity(
                database,
                output_dir=args.output_dir,
            )
            for database in args.databases
        ]
    except Exception as exc:
        print(f"Sensitivity analysis failed: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            [
                {
                    "result_path": response["result_path"],
                    "distance_csv_path": response["distance_csv_path"],
                    "map_name": response["result"]["map_name"],
                    "player_count": response["result"]["player_count"],
                }
                for response in responses
            ],
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

