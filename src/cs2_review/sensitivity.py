"""Threshold sensitivity experiments for existing behavior rules."""

from __future__ import annotations

import csv
import json
import math
import sqlite3
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cs2_review.metrics import list_players

NEAR_DISTANCE_THRESHOLDS = [300, 400, 500, 600, 700, 800]
FAR_DISTANCE_THRESHOLDS = [600, 700, 800, 900, 1000, 1200]
EARLY_WINDOWS_SECONDS = [5, 10, 15, 20, 25, 30]
SPAWN_NAMES = {"TSpawn", "CTSpawn"}


def _connect(database_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    return connection


def _distance(
    first: sqlite3.Row,
    second: sqlite3.Row,
) -> float | None:
    if None in {first["x"], first["y"], second["x"], second["y"]}:
        return None
    return math.hypot(
        float(first["x"]) - float(second["x"]),
        float(first["y"]) - float(second["y"]),
    )


def _nearest_distances(
    samples: list[sqlite3.Row],
    steamid: str,
) -> list[tuple[int, float]]:
    by_tick: dict[tuple[int, int], list[sqlite3.Row]] = defaultdict(list)
    for row in samples:
        by_tick[(int(row["round_num"]), int(row["tick"]))].append(row)

    result = []
    for (round_num, tick), rows in by_tick.items():
        player = next(
            (
                row for row in rows
                if str(row["steamid"]) == steamid
                and (row["health"] is None or int(row["health"]) > 0)
            ),
            None,
        )
        if player is None:
            continue
        distances = [
            value
            for row in rows
            if str(row["steamid"]) != steamid
            and row["side"] == player["side"]
            and (row["health"] is None or int(row["health"]) > 0)
            if (value := _distance(player, row)) is not None
        ]
        if distances:
            result.append((round_num, min(distances)))
    return result


def _early_first_places(
    connection: sqlite3.Connection,
    *,
    analysis_id: str,
    steamid: str,
    tick_rate: float,
) -> dict[int, dict[str, Any]]:
    rounds = connection.execute(
        """
        SELECT round_num, start_tick, freeze_end_tick
        FROM round
        WHERE analysis_id = ?
        ORDER BY round_num
        """,
        (analysis_id,),
    ).fetchall()
    results = {}
    for window in EARLY_WINDOWS_SECONDS:
        places_by_round = {}
        for round_row in rounds:
            round_num = int(round_row["round_num"])
            start_tick = (
                int(round_row["freeze_end_tick"])
                if round_row["freeze_end_tick"] is not None
                else int(round_row["start_tick"])
            )
            end_tick = start_tick + int(tick_rate * window)
            rows = connection.execute(
                """
                SELECT place_name
                FROM tick_sample
                WHERE analysis_id = ? AND steamid = ?
                  AND round_num = ? AND tick >= ? AND tick <= ?
                  AND health > 0
                ORDER BY tick
                """,
                (analysis_id, steamid, round_num, start_tick, end_tick),
            ).fetchall()
            first_place = next(
                (
                    str(row["place_name"])
                    for row in rows
                    if row["place_name"]
                    and row["place_name"] not in SPAWN_NAMES
                ),
                None,
            )
            if first_place:
                places_by_round[round_num] = first_place
        counts = Counter(places_by_round.values())
        dominant = counts.most_common(1)[0][0] if counts else None
        results[window] = {
            "rounds_with_route": len(places_by_round),
            "dominant_first_place": dominant,
            "dominant_consistency": (
                counts[dominant] / len(places_by_round)
                if dominant and places_by_round
                else None
            ),
            "distribution": dict(counts),
        }
    return results


def run_threshold_sensitivity(
    database_path: Path | str,
    *,
    output_dir: Path | str,
) -> dict[str, Any]:
    path = Path(database_path)
    connection = _connect(path)
    try:
        analysis = connection.execute("SELECT * FROM analysis").fetchone()
        if analysis is None:
            raise ValueError("No analysis record found")
        analysis_id = str(analysis["analysis_id"])
        tick_rate = float(analysis["tick_rate"] or 64.0)
        players = list_players(path)
        player_rows = []
        distance_rows = []
        early_rows = []
        for index, player in enumerate(players, start=1):
            label = f"P{index:02d}"
            samples = connection.execute(
                """
                SELECT round_num, tick, steamid, side, x, y, health, place_name
                FROM tick_sample
                WHERE analysis_id = ? AND steamid = ?
                UNION ALL
                SELECT round_num, tick, steamid, side, x, y, health, place_name
                FROM tick_sample
                WHERE analysis_id = ? AND steamid <> ?
                ORDER BY round_num, tick
                """,
                (analysis_id, player.steamid, analysis_id, player.steamid),
            ).fetchall()
            distances = _nearest_distances(samples, player.steamid)
            distance_values = [value for _, value in distances]
            early = _early_first_places(
                connection,
                analysis_id=analysis_id,
                steamid=player.steamid,
                tick_rate=tick_rate,
            )
            player_rows.append(
                {
                    "player_label": label,
                    "distance_sample_count": len(distance_values),
                    "distance_median": (
                        statistics.median(distance_values)
                        if distance_values
                        else None
                    ),
                }
            )
            for threshold in NEAR_DISTANCE_THRESHOLDS:
                ratio = (
                    sum(value <= threshold for value in distance_values)
                    / len(distance_values)
                    if distance_values
                    else None
                )
                distance_rows.append(
                    {
                        "player_label": label,
                        "comparison": "near",
                        "threshold": threshold,
                        "ratio": ratio,
                        "sample_count": len(distance_values),
                    }
                )
            for threshold in FAR_DISTANCE_THRESHOLDS:
                ratio = (
                    sum(value > threshold for value in distance_values)
                    / len(distance_values)
                    if distance_values
                    else None
                )
                distance_rows.append(
                    {
                        "player_label": label,
                        "comparison": "far",
                        "threshold": threshold,
                        "ratio": ratio,
                        "sample_count": len(distance_values),
                    }
                )
            for window, detail in early.items():
                early_rows.append(
                    {
                        "player_label": label,
                        "window_seconds": window,
                        **detail,
                    }
                )
    finally:
        connection.close()

    near_aggregate = []
    far_aggregate = []
    for threshold in NEAR_DISTANCE_THRESHOLDS:
        ratios = [
            row["ratio"] for row in distance_rows
            if row["comparison"] == "near"
            and row["threshold"] == threshold
            and row["ratio"] is not None
        ]
        near_aggregate.append(
            {
                "threshold": threshold,
                "player_mean_ratio": statistics.mean(ratios) if ratios else None,
                "player_ratio_min": min(ratios) if ratios else None,
                "player_ratio_max": max(ratios) if ratios else None,
            }
        )
    for threshold in FAR_DISTANCE_THRESHOLDS:
        ratios = [
            row["ratio"] for row in distance_rows
            if row["comparison"] == "far"
            and row["threshold"] == threshold
            and row["ratio"] is not None
        ]
        far_aggregate.append(
            {
                "threshold": threshold,
                "player_mean_ratio": statistics.mean(ratios) if ratios else None,
                "player_ratio_min": min(ratios) if ratios else None,
                "player_ratio_max": max(ratios) if ratios else None,
            }
        )

    early_aggregate = []
    for window in EARLY_WINDOWS_SECONDS:
        rows = [
            row for row in early_rows if row["window_seconds"] == window
        ]
        consistencies = [
            row["dominant_consistency"]
            for row in rows
            if row["dominant_consistency"] is not None
        ]
        early_aggregate.append(
            {
                "window_seconds": window,
                "player_mean_consistency": (
                    statistics.mean(consistencies)
                    if consistencies
                    else None
                ),
                "player_consistency_min": (
                    min(consistencies) if consistencies else None
                ),
                "player_consistency_max": (
                    max(consistencies) if consistencies else None
                ),
            }
        )

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    result = {
        "run_id": run_id,
        "database": path.name,
        "analysis_id": analysis_id,
        "map_name": analysis["map_name"],
        "player_count": len(players),
        "parameters": {
            "near_distance_thresholds": NEAR_DISTANCE_THRESHOLDS,
            "far_distance_thresholds": FAR_DISTANCE_THRESHOLDS,
            "early_windows_seconds": EARLY_WINDOWS_SECONDS,
        },
        "players": player_rows,
        "distance_aggregate": {
            "near": near_aggregate,
            "far": far_aggregate,
        },
        "early_window_aggregate": early_aggregate,
        "details": {
            "distance": distance_rows,
            "early_window": early_rows,
        },
        "notice": (
            "敏感性实验描述阈值变化如何影响本场规则结果，"
            "不等于分类准确率或参数最优性证明。"
        ),
    }

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    analysis_suffix = analysis_id[:8]
    result_path = destination / f"sensitivity_{analysis_suffix}_{run_id}.json"
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    csv_path = destination / (
        f"sensitivity_distance_{analysis_suffix}_{run_id}.csv"
    )
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "player_label",
                "comparison",
                "threshold",
                "ratio",
                "sample_count",
            ],
        )
        writer.writeheader()
        writer.writerows(distance_rows)
    return {
        "result_path": str(result_path.resolve()),
        "distance_csv_path": str(csv_path.resolve()),
        "result": result,
    }

