"""Import one CS2 demo into the local fact database.

Usage:
    .\\.venv\\Scripts\\python.exe scripts\\import_demo.py path\\to\\match.dem
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cs2_review.importer import import_demo  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Import a CS2 demo into SQLite.")
    parser.add_argument("demo", type=Path, help="Path to a .dem file")
    parser.add_argument("--output", type=Path, help="SQLite output path")
    parser.add_argument("--summary", type=Path, help="Optional JSON summary path")
    args = parser.parse_args()

    try:
        result = import_demo(args.demo, output_path=args.output)
    except Exception as exc:
        print(f"Import failed: {exc}", file=sys.stderr)
        return 1

    rendered = json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
    if args.summary:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

