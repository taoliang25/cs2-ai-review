"""Persist generated report drafts alongside their source FactBundle."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from cs2_review.reporting import ReportDraft


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def save_report(
    database_path: Path | str,
    *,
    fact_bundle: dict,
    report: ReportDraft,
) -> str:
    fact_bundle_json = _canonical_json(fact_bundle)
    fact_bundle_sha256 = hashlib.sha256(
        fact_bundle_json.encode("utf-8")
    ).hexdigest()
    report_id = hashlib.sha256(
        (
            fact_bundle_sha256
            + "|"
            + report.provider
            + "|"
            + (report.provider_model or "")
            + "|"
            + report.markdown
        ).encode("utf-8")
    ).hexdigest()[:32]

    connection = sqlite3.connect(Path(database_path))
    try:
        with connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO report (
                    report_id, analysis_id, steamid, provider, provider_model,
                    prompt_version, fact_bundle_sha256, status, report_markdown,
                    report_json, error_message, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'generated', ?, ?, NULL, ?)
                """,
                (
                    report_id,
                    fact_bundle["match"]["analysis_id"],
                    fact_bundle["player"]["steamid"],
                    report.provider,
                    report.provider_model,
                    report.structured.get("prompt_version"),
                    fact_bundle_sha256,
                    report.markdown,
                    json.dumps(report.structured, ensure_ascii=False),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
    finally:
        connection.close()
    return report_id

