"""Export an existing Markdown report to Word and PDF."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cs2_review.exporters import build_docx, build_pdf  # noqa: E402
from cs2_review.reporting import ReportDraft  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Export a report to DOCX and PDF.")
    parser.add_argument("markdown", type=Path)
    parser.add_argument("--facts", type=Path)
    parser.add_argument("--docx", type=Path, required=True)
    parser.add_argument("--pdf", type=Path, required=True)
    args = parser.parse_args()

    try:
        markdown = args.markdown.read_text(encoding="utf-8")
        facts = (
            json.loads(args.facts.read_text(encoding="utf-8"))
            if args.facts is not None
            else None
        )
        report = ReportDraft(
            provider="markdown-import",
            markdown=markdown,
            structured={"provider": "markdown-import"},
        )
        args.docx.parent.mkdir(parents=True, exist_ok=True)
        args.pdf.parent.mkdir(parents=True, exist_ok=True)
        args.docx.write_bytes(build_docx(markdown, fact_bundle=facts, report=report))
        args.pdf.write_bytes(build_pdf(markdown, fact_bundle=facts, report=report))
    except Exception as exc:
        print(f"Export failed: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {args.docx}")
    print(f"Wrote {args.pdf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

