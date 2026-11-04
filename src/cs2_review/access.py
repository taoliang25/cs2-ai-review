"""Lightweight access protection and local usage limits for the prototype."""

from __future__ import annotations

import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_USAGE_DB = PROJECT_ROOT / "data" / "runtime" / "usage.sqlite"
APP_TIMEZONE = ZoneInfo("Asia/Shanghai")


class UsageLimitError(RuntimeError):
    pass


def access_control_required() -> bool:
    return os.getenv("APP_REQUIRE_ACCESS", "false").lower() in {
        "1",
        "true",
        "yes",
    }


def access_code() -> str:
    return os.getenv("APP_ACCESS_CODE", "").strip()


def usage_limits_enabled() -> bool:
    return os.getenv("APP_ENFORCE_USAGE_LIMITS", "false").lower() in {
        "1",
        "true",
        "yes",
    }


@contextmanager
def analysis_slot(
    *,
    enabled: bool,
    database_path: Path | str = DEFAULT_USAGE_DB,
    max_concurrent: int = 5,
    max_daily_matches: int = 50,
) -> Iterator[None]:
    if not enabled:
        yield
        return

    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    local_now = now.astimezone(APP_TIMEZONE)
    day_start = local_now.replace(
        hour=0, minute=0, second=0, microsecond=0
    ).astimezone(timezone.utc)
    stale_before = now - timedelta(hours=2)
    connection = sqlite3.connect(path, timeout=10)
    try:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_slot (
                run_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT
            )
            """
        )
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            UPDATE analysis_slot
            SET status = 'abandoned', completed_at = ?
            WHERE status = 'running' AND started_at < ?
            """,
            (now.isoformat(), stale_before.isoformat()),
        )
        running = connection.execute(
            "SELECT COUNT(*) FROM analysis_slot WHERE status = 'running'"
        ).fetchone()[0]
        daily = connection.execute(
            """
            SELECT COUNT(*) FROM analysis_slot
            WHERE started_at >= ?
            """,
            (day_start.isoformat(),),
        ).fetchone()[0]
        if running >= max_concurrent:
            connection.rollback()
            raise UsageLimitError(
                f"当前已有 {running} 个分析任务，达到并发上限 "
                f"{max_concurrent}，请稍后重试。"
            )
        if daily >= max_daily_matches:
            connection.rollback()
            raise UsageLimitError(
                f"今日分析任务已达到上限 {max_daily_matches} 场，请明天再试。"
            )
        connection.execute(
            """
            INSERT INTO analysis_slot (run_id, status, started_at)
            VALUES (?, 'running', ?)
            """,
            (run_id, now.isoformat()),
        )
        connection.commit()
    finally:
        connection.close()

    try:
        yield
    finally:
        connection = sqlite3.connect(path, timeout=10)
        try:
            connection.execute(
                """
                UPDATE analysis_slot
                SET status = 'completed', completed_at = ?
                WHERE run_id = ?
                """,
                (datetime.now(timezone.utc).isoformat(), run_id),
            )
            connection.commit()
        finally:
            connection.close()

