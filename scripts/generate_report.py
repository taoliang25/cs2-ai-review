"""Generate a deterministic Markdown report from a player FactBundle."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cs2_review.reporting import TemplateReportProvider  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a template review report.")
    parser.add_argument("facts", type=Path, help="FactBundle JSON")
    parser.add_argument("--markdown", type=Path, required=True)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    try:
        bundle = json.loads(args.facts.read_text(encoding="utf-8"))
        report = TemplateReportProvider().generate(bundle)
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(report.markdown, encoding="utf-8")
        if args.json:
            args.json.parent.mkdir(parents=True, exist_ok=True)
            args.json.write_text(
                json.dumps(report.structured, ensure_ascii=False, indent=2)
                + "\n",
                encoding="utf-8",
            )
    except Exception as exc:
        print(f"Report generation failed: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {args.markdown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

