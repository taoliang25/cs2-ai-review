"""Run real parsing, data quality, and player metric experiments."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cs2_review.experiments import run_experiment  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run CS2 demo data experiments.")
    parser.add_argument(
        "--demo-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "demo",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "experiments",
    )
    args = parser.parse_args()

    demos = sorted(args.demo_dir.glob("*.dem"))
    try:
        response = run_experiment(demos, output_dir=args.output_dir)
    except Exception as exc:
        print(f"Experiment failed: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "result_path": response["result_path"],
                "metrics_csv_path": response["metrics_csv_path"],
                "demo_count": response["result"]["demo_count"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

