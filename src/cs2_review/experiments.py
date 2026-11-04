"""Reproducible single- or multi-demo data quality experiments."""

from __future__ import annotations

import csv
import importlib.metadata
import json
import platform
import sqlite3
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cs2_review.importer import import_demo
from cs2_review.metrics import analyze_player, list_players


def _connect(database_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    return connection


def _check(
    name: str,
    passed: bool,
    detail: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "status": "pass" if passed else "warning",
        "detail": detail,
    }


def _database_profile(database_path: Path) -> dict[str, Any]:
    connection = _connect(database_path)
    try:
        analysis = connection.execute("SELECT * FROM analysis").fetchone()
        if analysis is None:
            raise ValueError("Imported database has no analysis record")
        player_count = connection.execute(
            "SELECT COUNT(*) FROM player WHERE is_recorder = 0"
        ).fetchone()[0]
        round_count = connection.execute(
            "SELECT COUNT(*) FROM round"
        ).fetchone()[0]
        tick_count = connection.execute(
            "SELECT COUNT(*) FROM tick_sample"
        ).fetchone()[0]
        place_count = connection.execute(
            """
            SELECT COUNT(DISTINCT place_name)
            FROM tick_sample
            WHERE place_name IS NOT NULL AND place_name <> ''
            """
        ).fetchone()[0]
        null_position_count = connection.execute(
            """
            SELECT COUNT(*) FROM tick_sample
            WHERE x IS NULL OR y IS NULL
            """
        ).fetchone()[0]
        economy_count = connection.execute(
            "SELECT COUNT(*) FROM round_team_economy"
        ).fetchone()[0]
        event_counts = {
            str(row["event_type"]): int(row["n"])
            for row in connection.execute(
                """
                SELECT event_type, COUNT(*) AS n
                FROM game_event
                GROUP BY event_type
                ORDER BY event_type
                """
            ).fetchall()
        }
        side_counts = {
            str(row["starting_side"]): int(row["n"])
            for row in connection.execute(
                """
                SELECT starting_side, COUNT(*) AS n
                FROM player
                WHERE is_recorder = 0
                GROUP BY starting_side
                """
            ).fetchall()
        }
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_key_errors = connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()
    finally:
        connection.close()

    checks = [
        _check("sqlite_integrity", integrity == "ok", str(integrity)),
        _check(
            "foreign_keys",
            not foreign_key_errors,
            "无外键错误" if not foreign_key_errors else str(foreign_key_errors),
        ),
        _check(
            "regular_5v5_player_count",
            player_count == 10,
            f"有效玩家 {player_count} 名",
        ),
        _check(
            "two_teams",
            side_counts.get("terrorist") == 5
            and side_counts.get("counter-terrorist") == 5,
            str(side_counts),
        ),
        _check(
            "rounds_present",
            round_count > 0,
            f"回合数 {round_count}",
        ),
        _check(
            "position_samples",
            tick_count > 0 and null_position_count == 0,
            f"位置采样 {tick_count} 行，空坐标 {null_position_count} 行",
        ),
        _check(
            "place_names",
            place_count > 0,
            f"地图地点 {place_count} 个",
        ),
        _check(
            "team_economy",
            economy_count == round_count * 2,
            f"经济记录 {economy_count}，期望 {round_count * 2}",
        ),
        _check(
            "core_events",
            all(name in event_counts for name in ["kill", "damage"]),
            f"关键事件类型 {sorted(event_counts)}",
        ),
        _check(
            "match_end_event",
            bool(analysis["has_match_end"]),
            "发现 cs_win_panel_match"
            if analysis["has_match_end"]
            else "未发现完整比赛结束事件",
        ),
        _check(
            "regulation_round_target_reached",
            bool(analysis["regulation_complete"]),
            "达到常规赛目标得分"
            if analysis["regulation_complete"]
            else "未达到常规赛目标得分，可能是投降、片段或非常规模式",
        ),
    ]
    return {
        "analysis_id": str(analysis["analysis_id"]),
        "demo_sha256": str(analysis["demo_sha256"]),
        "map_name": analysis["map_name"],
        "player_count": player_count,
        "round_count": round_count,
        "has_match_end": bool(analysis["has_match_end"]),
        "regulation_complete": bool(analysis["regulation_complete"]),
        "tick_sample_count": tick_count,
        "place_name_count": place_count,
        "economy_record_count": economy_count,
        "event_counts": event_counts,
        "checks": checks,
    }


def _player_metric_rows(
    database_path: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], set[str]]:
    players = list_players(database_path)
    player_summaries = []
    metric_rows = []
    for index, player in enumerate(players, start=1):
        player_label = f"P{index:02d}"
        started = time.perf_counter()
        bundle = analyze_player(database_path, steamid=player.steamid)
        elapsed = time.perf_counter() - started
        player_summaries.append(
            {
                "player_label": player_label,
                "starting_side": player.starting_side,
                "analysis_seconds": round(elapsed, 4),
                "metric_count": len(bundle["metrics"]),
                "round_count": len(bundle["rounds"]),
                "evidence_count": len(bundle["evidence"]),
                "tactical_pattern_rule_version": bundle[
                    "tactical_patterns"
                ]["rule_version"],
                "tactical_pattern_summary": bundle[
                    "tactical_patterns"
                ]["summary"],
                "key_rounds": {
                    key: (
                        value.get("round_num")
                        if isinstance(value, dict)
                        else len(value)
                    )
                    for key, value in bundle["key_rounds"].items()
                },
            }
        )
        for metric in bundle["metrics"]:
            metric_rows.append(
                {
                    "player_label": player_label,
                    "metric_key": metric["key"],
                    "value": (
                        json.dumps(metric["value"], ensure_ascii=False)
                        if isinstance(metric["value"], (dict, list))
                        else metric["value"]
                    ),
                    "unit": metric["unit"],
                    "sample_size": metric["sample_size"],
                    "confidence": metric["confidence"],
                    "evidence_count": len(metric["evidence_ids"]),
                }
            )
    return player_summaries, metric_rows, {
        player.steamid for player in players
    }


def run_experiment(
    demo_paths: list[Path | str],
    *,
    output_dir: Path | str,
) -> dict[str, Any]:
    paths = [Path(path) for path in demo_paths]
    if not paths:
        raise ValueError("No .dem files were provided")
    for path in paths:
        if not path.is_file() or path.suffix.lower() != ".dem":
            raise ValueError(f"Invalid demo path: {path}")

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    demo_results = []
    all_metrics = []
    unique_participants: set[str] = set()
    complete_participants: set[str] = set()

    with tempfile.TemporaryDirectory(prefix="cs2-review-experiment-") as temp:
        temp_dir = Path(temp)
        for index, demo_path in enumerate(paths, start=1):
            database_path = temp_dir / f"demo_{index:03d}.sqlite"
            parse_started = time.perf_counter()
            import_result = import_demo(
                demo_path,
                output_path=database_path,
            )
            parse_seconds = time.perf_counter() - parse_started
            database_profile = _database_profile(database_path)
            player_summaries, metric_rows, participant_ids = (
                _player_metric_rows(database_path)
            )
            unique_participants.update(participant_ids)
            if import_result.regulation_complete:
                complete_participants.update(participant_ids)
            for row in metric_rows:
                row["demo_index"] = index
                all_metrics.append(row)
            demo_results.append(
                {
                    "demo_index": index,
                    "source_filename": demo_path.name,
                    "source_size_bytes": demo_path.stat().st_size,
                    "parse_seconds": round(parse_seconds, 4),
                    **database_profile,
                    "players": player_summaries,
                }
            )

    result = {
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "awpy": importlib.metadata.version("awpy"),
            "demoparser2": importlib.metadata.version("demoparser2"),
        },
        "demo_count": len(paths),
        "participant_counts": {
            "all_unique": len(unique_participants),
            "complete_unique": len(complete_participants),
            "all_demo_player_records": sum(
                int(demo["player_count"]) for demo in demo_results
            ),
        },
        "demos": demo_results,
        "metrics": all_metrics,
        "notice": (
            "这是解析与数据质量实验结果，不是战术识别准确率。"
            "玩家名称和 Steam ID 已从实验输出中移除。"
        ),
    }
    result_path = output / f"experiment_{run_id}.json"
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    metrics_path = output / f"player_metrics_{run_id}.csv"
    with metrics_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(all_metrics[0]))
        writer.writeheader()
        writer.writerows(all_metrics)
    return {
        "result_path": str(result_path.resolve()),
        "metrics_csv_path": str(metrics_path.resolve()),
        "result": result,
    }

