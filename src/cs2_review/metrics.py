"""Transparent player behavior metrics built from the normalized fact store."""

from __future__ import annotations

import bisect
import json
import math
import sqlite3
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import median
from typing import Any, Iterable

RULE_VERSION = "event-rules-v0.1"
NEAR_TEAMMATE_DISTANCE = 500.0
FAR_TEAMMATE_DISTANCE = 800.0
SUPPORT_DISTANCE = 800.0
SUPPORT_LOOKAHEAD_SECONDS = 5.0
EARLY_ROUTE_SECONDS = 15.0
SPAWN_NAMES = {"TSpawn", "CTSpawn"}


@dataclass(frozen=True)
class PlayerOption:
    steamid: str
    name: str
    starting_side: str | None


def _connect(database_path: Path | str) -> sqlite3.Connection:
    connection = sqlite3.connect(Path(database_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def list_players(database_path: Path | str) -> list[PlayerOption]:
    connection = _connect(database_path)
    try:
        rows = connection.execute(
            """
            SELECT steamid, current_name, starting_side
            FROM player
            WHERE is_recorder = 0
            ORDER BY starting_side, current_name
            """
        ).fetchall()
    finally:
        connection.close()
    return [
        PlayerOption(
            steamid=str(row["steamid"]),
            name=str(row["current_name"]),
            starting_side=row["starting_side"],
        )
        for row in rows
    ]


def _distance(
    x1: float | None, y1: float | None, x2: float | None, y2: float | None
) -> float | None:
    if None in (x1, y1, x2, y2):
        return None
    return math.hypot(float(x1) - float(x2), float(y1) - float(y2))


def _ratio(numerator: int | float, denominator: int | float) -> float | None:
    if not denominator:
        return None
    return float(numerator) / float(denominator)


def _payload(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    raw = row["payload_json"]
    return json.loads(raw) if raw else {}


def _event_is_post_round(row: sqlite3.Row | dict[str, Any]) -> bool:
    return bool(_payload(row).get("is_post_round"))


def _metric(
    key: str,
    label: str,
    value: float | int | str | None,
    *,
    unit: str | None = None,
    sample_size: int = 1,
    confidence: float | None = None,
    evidence_ids: Iterable[str] = (),
    definition: str | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "value": value,
        "unit": unit,
        "sample_size": sample_size,
        "confidence": confidence,
        "evidence_ids": list(dict.fromkeys(evidence_ids)),
        "definition": definition,
    }


def _sample_evidence_id(
    round_num: int, tick: int, steamid: str
) -> str:
    return f"S-R{round_num:02d}-T{tick:07d}-{steamid[-6:]}"


def _build_teammate_death_contexts(
    *,
    round_num: int,
    steamid: str,
    side: str | None,
    tick_rate: float,
    freeze_end: int,
    visible_events: list[sqlite3.Row],
    samples_by_tick: dict[tuple[int, int], list[sqlite3.Row]],
    sample_ticks: list[int],
    evidence: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    if side is None:
        return []
    contexts = []
    bomb_plants = [
        row for row in visible_events if row["event_type"] == "finish_plant"
    ]
    for event in visible_events:
        if event["event_type"] != "kill":
            continue
        payload = _payload(event)
        victim_id = (
            str(event["target_steamid"])
            if event["target_steamid"] is not None
            else None
        )
        if (
            victim_id is None
            or victim_id == steamid
            or payload.get("victim_side") != side
        ):
            continue
        death_tick = int(event["tick"])
        insertion = bisect.bisect_left(sample_ticks, death_tick)
        candidates = sample_ticks[
            max(0, insertion - 1):min(len(sample_ticks), insertion + 2)
        ]
        nearest_tick = (
            min(candidates, key=lambda value: abs(value - death_tick))
            if candidates
            else None
        )
        tick_rows = (
            samples_by_tick.get((round_num, nearest_tick), [])
            if nearest_tick is not None
            else []
        )
        player_row = next(
            (
                row for row in tick_rows
                if str(row["steamid"]) == steamid
            ),
            None,
        )
        victim_row = next(
            (
                row for row in tick_rows
                if str(row["steamid"]) == victim_id
            ),
            None,
        )
        alive_teammates = [
            row for row in tick_rows
            if row["side"] == side
            and str(row["steamid"]) != steamid
            and (row["health"] is None or int(row["health"]) > 0)
        ]
        nearest_teammate = None
        nearest_teammate_distance = None
        if player_row is not None:
            teammate_options = []
            for row in alive_teammates:
                distance = _distance(
                    player_row["x"],
                    player_row["y"],
                    row["x"],
                    row["y"],
                )
                if distance is not None:
                    teammate_options.append((distance, row))
            if teammate_options:
                nearest_teammate_distance, nearest_teammate = min(
                    teammate_options, key=lambda item: item[0]
                )

        distance_to_death = (
            _distance(
                player_row["x"],
                player_row["y"],
                victim_row["x"],
                victim_row["y"],
            )
            if player_row is not None and victim_row is not None
            else None
        )
        own_alive = sum(
            1
            for row in tick_rows
            if row["side"] == side
            and (row["health"] is None or int(row["health"]) > 0)
        )
        enemy_alive = sum(
            1
            for row in tick_rows
            if row["side"] not in {None, side}
            and (row["health"] is None or int(row["health"]) > 0)
        )
        prior_plants = [
            row for row in bomb_plants if int(row["tick"]) <= death_tick
        ]
        latest_plant = max(prior_plants, key=lambda row: int(row["tick"])) if prior_plants else None
        bombsite = (
            _payload(latest_plant).get("bombsite")
            if latest_plant is not None
            else None
        )
        has_bomb = bool(player_row and player_row["has_bomb"])
        player_alive = bool(
            player_row is not None
            and (
                player_row["health"] is None
                or int(player_row["health"]) > 0
            )
        )

        suggestions = []
        if player_alive:
            teammate_place = (
                nearest_teammate["place_name"]
                if nearest_teammate is not None
                else None
            )
            if (
                nearest_teammate is not None
                and nearest_teammate_distance is not None
                and nearest_teammate_distance > 800
            ):
                suggestions.append(
                    "优先重新汇合"
                    + (f"到最近存活队友所在的 {teammate_place}" if teammate_place else "")
                    + "，避免在人数劣势下继续跨区域单独施压。"
                )
            elif (
                nearest_teammate is not None
                and nearest_teammate_distance is not None
                and nearest_teammate_distance <= 800
            ):
                suggestions.append(
                    "与同区域队友保持交叉火力，避免沿队友刚被击杀的同一枪线重复暴露。"
                )
            if has_bomb:
                suggestions.append(
                    "当前携带炸弹，应先确认最近存活队友位置和可安放区域，"
                    "不要在缺少掩护时独自冲向下包点。"
                )
            if latest_plant is not None:
                if side == "counter-terrorist":
                    suggestions.append(
                        f"炸弹已安放于 {bombsite or '包点'}，"
                        "优先围绕回防信息和拆包条件行动。"
                    )
                else:
                    suggestions.append(
                        f"炸弹已安放于 {bombsite or '包点'}，"
                        "优先利用掩体和队友形成守包交叉火力。"
                    )
            if own_alive == 1 and enemy_alive >= 1:
                suggestions.append(
                    "已进入最后存活状态，需比较主动找信息、保枪和尝试目标之间的风险。"
                )
            if not suggestions:
                suggestions.append(
                    "根据最近存活队友的位置选择汇合或保持交叉火力，"
                    "不要在缺少信息时盲目追击击杀者。"
                )

        event_id = str(event["evidence_id"])
        sample_id = (
            _sample_evidence_id(round_num, nearest_tick, steamid)
            if nearest_tick is not None
            else None
        )
        if sample_id:
            evidence[sample_id] = {
                "evidence_id": sample_id,
                "type": "teammate_death_context",
                "round_num": round_num,
                "tick": nearest_tick,
                "summary": (
                    f"队友在 {victim_row['place_name'] if victim_row else '未知区域'}"
                    f"阵亡时，目标玩家在 "
                    f"{player_row['place_name'] if player_row else '未知区域'}"
                ),
            }
        contexts.append(
            {
                "evidence_ids": [
                    item for item in [event_id, sample_id] if item
                ],
                "teammate_death_tick": death_tick,
                "seconds_since_freeze": round(max(0.0, (death_tick - freeze_end) / tick_rate), 1),
                "teammate_death_place": (
                    victim_row["place_name"] if victim_row else None
                ),
                "player_place": (
                    player_row["place_name"] if player_row else None
                ),
                "player_alive": player_alive,
                "distance_to_teammate_death": distance_to_death,
                "nearest_alive_teammate_place": (
                    nearest_teammate["place_name"]
                    if nearest_teammate is not None
                    else None
                ),
                "distance_to_nearest_alive_teammate": nearest_teammate_distance,
                "teammates_alive": own_alive,
                "enemies_alive": enemy_alive,
                "player_has_bomb": has_bomb,
                "bomb_planted": latest_plant is not None,
                "bombsite": bombsite,
                "suggestions": suggestions,
            }
        )
    return contexts


def _build_round_narrative(
    *,
    round_num: int,
    steamid: str,
    tick_rate: float,
    freeze_end: int,
    team_won: bool | None,
    visible_events: list[sqlite3.Row],
    round_samples: list[sqlite3.Row],
    first_exit: str | None,
    early_sequence: list[str],
    kills: list[sqlite3.Row],
    deaths: list[sqlite3.Row],
    survived: bool,
    support_distance: float | None,
    support_responded: bool,
    utility_events: dict[str, int],
    evidence_ids: list[str],
    teammate_death_contexts: list[dict[str, Any]],
) -> dict[str, Any]:
    damage_events = [
        row for row in visible_events if row["event_type"] == "damage"
    ]
    kill_events = [
        row for row in visible_events if row["event_type"] == "kill"
    ]
    first_damage = damage_events[0] if damage_events else None
    first_kill = kill_events[0] if kill_events else None
    player_death = deaths[0] if deaths else None
    objective_events = [
        row for row in visible_events
        if row["event_type"] in {"finish_plant", "defuse", "explode"}
    ]

    observations = []
    if first_exit:
        route_text = " → ".join(early_sequence[:4]) or first_exit
        observations.append(f"前 15 秒从出生区进入 {route_text}")
    if first_damage:
        if first_damage["actor_steamid"] == steamid:
            observations.append("目标玩家先对对手造成伤害")
        elif first_damage["target_steamid"] == steamid:
            observations.append("目标玩家先被对手命中")
        else:
            observations.append("首轮交火发生在其他队员与对手之间")
    if first_kill:
        if first_kill["actor_steamid"] == steamid:
            observations.append("取得本回合首杀")
        elif first_kill["target_steamid"] == steamid:
            observations.append("成为本回合首死")
    if player_death:
        death_tick = int(player_death["tick"])
        prior_samples = [
            row for row in round_samples if int(row["tick"]) <= death_tick
        ]
        place = (
            prior_samples[-1]["place_name"] if prior_samples else None
        )
        seconds = max(0.0, (death_tick - freeze_end) / tick_rate)
        observations.append(
            f"于行动开始后约 {seconds:.0f} 秒阵亡"
            + (f"，地点为 {place}" if place else "")
        )
    elif survived:
        observations.append("本回合结束时仍在存活状态")
    if teammate_death_contexts:
        first_death = teammate_death_contexts[0]
        observations.append(
            "队友首次阵亡时，目标玩家位于 "
            f"{first_death['player_place'] or '未知区域'}"
            + (
                f"，距阵亡位置约 "
                f"{first_death['distance_to_teammate_death']:.0f}"
                if isinstance(
                    first_death["distance_to_teammate_death"],
                    (int, float),
                )
                else ""
            )
        )
    if objective_events:
        labels = {
            "finish_plant": "完成炸弹安放",
            "defuse": "完成炸弹拆除",
            "explode": "炸弹爆炸",
        }
        observations.append(
            "、".join(
                labels.get(row["event_type"], row["event_type"])
                for row in objective_events
            )
        )

    impact = []
    if first_kill and first_kill["actor_steamid"] == steamid:
        impact.append("首杀使本方在回合早期取得人数优势")
    if first_kill and first_kill["target_steamid"] == steamid:
        impact.append("首死使本方在回合早期少一人")
    if kills:
        impact.append(f"完成 {len(kills)} 次击杀")
    if deaths and not kills:
        impact.append("该回合阵亡且未取得击杀")
    if team_won is True:
        impact.append("队伍最终赢下回合")
    elif team_won is False:
        impact.append("队伍最终输掉回合")
    if survived and team_won is False:
        impact.append("目标玩家存活但队伍未赢下回合")

    alternatives = []
    if first_kill and first_kill["target_steamid"] == steamid:
        alternatives.append(
            "回看首次交战是否具备队友补枪或道具保护；"
            "若缺少支援，可考虑降低首轮交火风险并等待交易机会。"
        )
    if support_distance is not None and support_distance > 800:
        alternatives.append(
            "队友接敌时双方距离较远，可检查提前换位或缩短支援路径是否更有利。"
        )
    elif support_distance is not None and not support_responded:
        alternatives.append(
            "队友接敌时距离不远，可检查为什么 5 秒内没有形成伤害或击杀响应。"
        )
    if survived and team_won is False:
        alternatives.append(
            "存活残局中可比较主动获取信息、与剩余队友汇合以及保枪的收益。"
        )
    if team_won is True and first_kill and first_kill["actor_steamid"] == steamid:
        alternatives.append(
            "检查人数优势形成后是继续压迫还是重新集合，"
            "并区分可重复配合与对手临时失误。"
        )
    for context in teammate_death_contexts[:2]:
        alternatives.extend(context.get("suggestions", []))
    if not alternatives:
        alternatives.append(
            "结合当时人数、经济和队友位置，比较继续执行原计划、"
            "重新集合或保留资源的风险与收益。"
        )

    summary = (
        f"第 {round_num} 回合，"
        + ("；".join(observations) if observations else "可观测事件不足")
        + "。"
    )
    return {
        "summary": summary,
        "observations": observations,
        "impact": impact,
        "alternatives": alternatives,
        "utility_events": utility_events,
        "teammate_death_contexts": teammate_death_contexts,
        "evidence_ids": list(dict.fromkeys(evidence_ids)),
    }


def _round_score_states(
    rounds: list[sqlite3.Row],
    player_side_by_round: dict[int, str | None],
) -> dict[int, dict[str, Any]]:
    scores: Counter[str] = Counter()
    states: dict[int, dict[str, Any]] = {}
    for row in rounds:
        round_num = int(row["round_num"])
        side = player_side_by_round.get(round_num)
        if side is None:
            states[round_num] = {
                "selected_side": None,
                "score_before": None,
                "score_difference": None,
                "game_state": "unknown",
                "team_won": None,
            }
        else:
            opponent = (
                "counter-terrorist" if side == "terrorist" else "terrorist"
            )
            difference = scores[side] - scores[opponent]
            game_state = (
                "leading"
                if difference > 0
                else "trailing"
                if difference < 0
                else "tied"
            )
            states[round_num] = {
                "selected_side": side,
                "score_before": {
                    "selected_team": scores[side],
                    "opponent": scores[opponent],
                },
                "score_difference": difference,
                "game_state": game_state,
                "team_won": row["winner_side"] == side,
            }
        winner = str(row["winner_side"])
        if winner == "counter-terrain":
            winner = "counter-terrorist"
        scores[winner] += 1
    return states


def _build_metrics(
    *,
    connection: sqlite3.Connection,
    analysis: sqlite3.Row,
    player: sqlite3.Row,
) -> dict[str, Any]:
    steamid = str(player["steamid"])
    analysis_id = str(analysis["analysis_id"])
    tick_rate = float(analysis["tick_rate"] or 64.0)

    rounds = connection.execute(
        "SELECT * FROM round ORDER BY round_num"
    ).fetchall()
    economy = connection.execute(
        "SELECT * FROM round_team_economy"
    ).fetchall()
    samples = connection.execute(
        """
        SELECT * FROM tick_sample
        WHERE analysis_id = ?
        ORDER BY round_num, tick
        """,
        (analysis["analysis_id"],),
    ).fetchall()
    events = connection.execute(
        """
        SELECT * FROM game_event
        WHERE analysis_id = ?
        ORDER BY round_num, tick, evidence_id
        """,
        (analysis["analysis_id"],),
    ).fetchall()

    round_by_num = {int(row["round_num"]): row for row in rounds}
    economy_by_round_side = {
        (int(row["round_num"]), str(row["side"])): row for row in economy
    }
    samples_by_round_tick: dict[tuple[int, int], list[sqlite3.Row]] = defaultdict(
        list
    )
    samples_by_round_player: dict[int, list[sqlite3.Row]] = defaultdict(list)
    sample_ticks_by_round: dict[int, list[int]] = defaultdict(list)
    for row in samples:
        round_num = int(row["round_num"])
        samples_by_round_tick[(round_num, int(row["tick"]))].append(row)
        if str(row["steamid"]) == steamid:
            samples_by_round_player[round_num].append(row)
        if int(row["tick"]) not in sample_ticks_by_round[round_num]:
            sample_ticks_by_round[round_num].append(int(row["tick"]))
    for round_ticks in sample_ticks_by_round.values():
        round_ticks.sort()

    player_side_votes: dict[int, Counter[str]] = defaultdict(Counter)
    for round_num, round_samples in samples_by_round_player.items():
        for row in round_samples:
            if row["side"] is not None:
                player_side_votes[round_num][str(row["side"])] += 1
    player_side_by_round = {
        round_num: votes.most_common(1)[0][0]
        if votes
        else player["starting_side"]
        for round_num, votes in player_side_votes.items()
    }
    score_states = _round_score_states(rounds, player_side_by_round)

    events_by_round: dict[int, list[sqlite3.Row]] = defaultdict(list)
    for row in events:
        events_by_round[int(row["round_num"])].append(row)

    evidence: dict[str, dict[str, Any]] = {}
    round_facts: list[dict[str, Any]] = []
    match_kills = 0
    match_deaths = 0
    match_assists = 0
    opening_contacts = 0
    opening_kills = 0
    opening_deaths = 0
    group_distances: list[float] = []
    first_exit_places: list[str] = []
    early_route_sequences: list[list[str]] = []
    top_place_counter: Counter[str] = Counter()
    state_distances: dict[str, list[float]] = defaultdict(list)
    support_eligible = 0
    support_nearby = 0
    support_responses = 0
    clutch_rounds: list[dict[str, Any]] = []
    kill_evidence_ids: list[str] = []
    death_evidence_ids: list[str] = []
    assist_evidence_ids: list[str] = []
    opening_evidence_ids: list[str] = []
    route_evidence_ids: list[str] = []
    support_evidence_ids: list[str] = []
    utility_evidence_ids: list[str] = []
    purchase_evidence_ids: list[str] = []
    clutch_evidence_ids: list[str] = []
    utility_totals: Counter[str] = Counter()
    utility_rounds: set[int] = set()
    item_purchase_totals: Counter[str] = Counter()

    for round_row in rounds:
        round_num = int(round_row["round_num"])
        round_evidence_id = (
            f"R-{analysis_id[:8].upper()}-R{round_num:02d}"
        )
        evidence[round_evidence_id] = {
            "evidence_id": round_evidence_id,
            "type": "round_context",
            "round_num": round_num,
            "tick": int(round_row["start_tick"]),
            "summary": (
                f"第 {round_num} 回合由 {round_row['winner_side']} 获胜，"
                f"结束原因 {round_row['reason_name'] or '未知'}"
            ),
        }
        start_tick = int(round_row["start_tick"])
        freeze_end = (
            int(round_row["freeze_end_tick"])
            if round_row["freeze_end_tick"] is not None
            else start_tick
        )
        end_tick = int(round_row["end_tick"])
        side = player_side_by_round.get(round_num)
        round_samples = samples_by_round_player.get(round_num, [])
        visible_events = [
            row for row in events_by_round.get(round_num, [])
            if not _event_is_post_round(row)
        ]

        kills = [
            row for row in visible_events
            if row["event_type"] == "kill" and row["actor_steamid"] == steamid
        ]
        deaths = [
            row for row in visible_events
            if row["event_type"] == "kill" and row["target_steamid"] == steamid
        ]
        assists = [
            row for row in visible_events
            if row["event_type"] == "kill" and row["assister_steamid"] == steamid
        ]
        damage_events = [
            row for row in visible_events if row["event_type"] == "damage"
        ]
        kill_events = [
            row for row in visible_events if row["event_type"] == "kill"
        ]
        first_damage = damage_events[0] if damage_events else None
        first_kill = kill_events[0] if kill_events else None
        opening_contact = bool(
            first_damage
            and steamid
            in {first_damage["actor_steamid"], first_damage["target_steamid"]}
        )
        opening_kill = bool(
            first_kill and first_kill["actor_steamid"] == steamid
        )
        opening_death = bool(
            first_kill and first_kill["target_steamid"] == steamid
        )
        kill_evidence_ids.extend(str(row["evidence_id"]) for row in kills)
        death_evidence_ids.extend(str(row["evidence_id"]) for row in deaths)
        assist_evidence_ids.extend(str(row["evidence_id"]) for row in assists)
        if first_damage and opening_contact:
            opening_evidence_ids.append(str(first_damage["evidence_id"]))
        round_evidence_ids = [
            str(row["evidence_id"]) for row in visible_events
            if steamid
            in {
                row["actor_steamid"],
                row["target_steamid"],
                row["assister_steamid"],
            }
        ]
        evidence_priority = {
            "kill": 0,
            "damage": 1,
            "finish_plant": 2,
            "start_plant": 3,
            "defuse": 4,
            "flash_blind": 5,
            "smoke": 6,
            "fire": 7,
            "item_purchase": 8,
        }
        decision_evidence_ids = [
            str(row["evidence_id"])
            for row in sorted(
                visible_events,
                key=lambda row: (
                    evidence_priority.get(row["event_type"], 99),
                    int(row["tick"]),
                ),
            )
            if steamid
            in {
                row["actor_steamid"],
                row["target_steamid"],
                row["assister_steamid"],
            }
        ]
        for event_row in visible_events:
            event_id = str(event_row["evidence_id"])
            if event_id not in round_evidence_ids:
                continue
            event_payload = _payload(event_row)
            evidence[event_id] = {
                "evidence_id": event_id,
                "type": event_row["event_type"],
                "round_num": round_num,
                "tick": int(event_row["tick"]),
                "actor_name": event_payload.get("attacker_name")
                or event_payload.get("user_name")
                or event_payload.get("name"),
                "target_name": event_payload.get("victim_name"),
                "weapon": event_row["weapon"],
                "x": event_row["x"],
                "y": event_row["y"],
                "summary": (
                    f"{event_row['event_type']} 事件，"
                    f"行动者="
                    f"{'目标玩家' if event_row['actor_steamid'] == steamid else '其他参赛者' if event_row['actor_steamid'] else '无'}，"
                    f"目标="
                    f"{'目标玩家' if event_row['target_steamid'] == steamid else '其他参赛者' if event_row['target_steamid'] else '无'}"
                ),
            }

        active_samples = [
            row for row in round_samples
            if int(row["tick"]) >= freeze_end
            and (row["health"] is None or int(row["health"]) > 0)
        ]
        action_samples = [
            row for row in active_samples
            if row["place_name"] and row["place_name"] not in SPAWN_NAMES
        ]
        places = [
            str(row["place_name"]) for row in action_samples if row["place_name"]
        ]
        top_place_counter.update(places)
        first_exit = places[0] if places else None
        if first_exit:
            first_exit_places.append(first_exit)
            first_exit_row = action_samples[
                next(
                    index
                    for index, row in enumerate(action_samples)
                    if row["place_name"] == first_exit
                )
            ]
            sample_id = _sample_evidence_id(
                round_num, int(first_exit_row["tick"]), steamid
            )
            round_evidence_ids.append(sample_id)
            route_evidence_ids.append(sample_id)
            evidence[sample_id] = {
                "evidence_id": sample_id,
                "type": "route_sample",
                "round_num": round_num,
                "tick": int(first_exit_row["tick"]),
                "place_name": first_exit,
                "x": first_exit_row["x"],
                "y": first_exit_row["y"],
                "summary": f"有效行动阶段首次到达 {first_exit}",
            }
        early_end = freeze_end + int(tick_rate * EARLY_ROUTE_SECONDS)
        early_sequence = list(
            dict.fromkeys(
                str(row["place_name"])
                for row in action_samples
                if int(row["tick"]) <= early_end and row["place_name"]
            )
        )
        if early_sequence:
            early_route_sequences.append(early_sequence)

        round_distances: list[float] = []
        for round_tick, tick_rows in samples_by_round_tick.items():
            if round_tick[0] != round_num:
                continue
            player_row = next(
                (
                    row for row in tick_rows
                    if str(row["steamid"]) == steamid
                    and (row["health"] is None or int(row["health"]) > 0)
                ),
                None,
            )
            if player_row is None:
                continue
            distances = [
                distance
                for row in tick_rows
                if str(row["steamid"]) != steamid
                and row["side"] == player_row["side"]
                and (row["health"] is None or int(row["health"]) > 0)
                if (
                    distance := _distance(
                        player_row["x"],
                        player_row["y"],
                        row["x"],
                        row["y"],
                    )
                )
                is not None
            ]
            if distances:
                nearest = min(distances)
                round_distances.append(nearest)
                group_distances.append(nearest)
                state_distances[
                    score_states[round_num]["game_state"]
                ].append(nearest)

        last_live_player_sample = next(
            (
                row for row in reversed(round_samples)
                if int(row["tick"]) <= end_tick
            ),
            None,
        )
        survived = bool(
            last_live_player_sample
            and (
                last_live_player_sample["health"] is None
                or int(last_live_player_sample["health"]) > 0
            )
        )

        # A clutch is observed when the selected player is the only living
        # teammate while at least one opponent is alive.
        for (sample_round, tick), tick_rows in samples_by_round_tick.items():
            if sample_round != round_num or side is None:
                continue
            player_row = next(
                (
                    row for row in tick_rows
                    if str(row["steamid"]) == steamid
                ),
                None,
            )
            if not player_row or (
                player_row["health"] is not None
                and int(player_row["health"]) <= 0
            ):
                continue
            own_alive = sum(
                1
                for row in tick_rows
                if row["side"] == side
                and (row["health"] is None or int(row["health"]) > 0)
            )
            enemy_alive = sum(
                1
                for row in tick_rows
                if row["side"] not in {None, side}
                and (row["health"] is None or int(row["health"]) > 0)
            )
            if own_alive == 1 and enemy_alive >= 1:
                clutch_sample_id = _sample_evidence_id(
                    round_num, tick, steamid
                )
                clutch_evidence_ids.append(clutch_sample_id)
                evidence[clutch_sample_id] = {
                    "evidence_id": clutch_sample_id,
                    "type": "clutch_context",
                    "round_num": round_num,
                    "tick": tick,
                    "enemies_alive": enemy_alive,
                    "summary": (
                        f"该采样中玩家为本方唯一存活成员，"
                        f"剩余敌人 {enemy_alive} 名"
                    ),
                }
                clutch_rounds.append(
                    {
                        "round_num": round_num,
                        "tick": tick,
                        "enemies_alive": enemy_alive,
                        "team_won": score_states[round_num]["team_won"],
                    }
                )
                break

        # Utility effect evidence. Current normalized data has smoke/fire
        # effects and flash-blind outcomes; purchases indicate intent.
        round_utility = Counter()
        for row in visible_events:
            if row["actor_steamid"] != steamid:
                continue
            if row["event_type"] in {"smoke", "fire"}:
                round_utility[row["event_type"]] += 1
                utility_totals[row["event_type"]] += 1
                round_evidence_ids.append(str(row["evidence_id"]))
                utility_evidence_ids.append(str(row["evidence_id"]))
            elif row["event_type"] == "flash_blind":
                round_utility["flash_blind"] += 1
                utility_totals["flash_blind"] += 1
                round_evidence_ids.append(str(row["evidence_id"]))
                utility_evidence_ids.append(str(row["evidence_id"]))
            elif row["event_type"].startswith("item_"):
                item = str(row["weapon"] or "unknown")
                if row["event_type"] == "item_purchase":
                    item_purchase_totals[item] += 1
                    purchase_evidence_ids.append(str(row["evidence_id"]))
            elif (
                row["event_type"] == "damage"
                and row["weapon"] in {"hegrenade", "molotov", "inferno", "incgrenade"}
            ):
                round_utility["utility_damage"] += 1
                utility_totals["utility_damage"] += 1
                round_evidence_ids.append(str(row["evidence_id"]))
                utility_evidence_ids.append(str(row["evidence_id"]))
        if sum(round_utility.values()):
            utility_rounds.add(round_num)

        # First teammate combat contact and the selected player's distance to
        # that teammate. This is an observable support-context metric.
        teammate_contact = None
        for event in damage_events:
            payload = _payload(event)
            actor_side = payload.get("attacker_side")
            target_side = payload.get("victim_side")
            actor = event["actor_steamid"]
            target = event["target_steamid"]
            if actor != steamid and actor_side == side:
                teammate_contact = (event, actor, target)
                break
            if target != steamid and target_side == side:
                teammate_contact = (event, target, actor)
                break
        support_distance = None
        support_responded = False
        if teammate_contact and side is not None:
            contact_event, teammate_id, opponent_id = teammate_contact
            contact_tick = int(contact_event["tick"])
            available_ticks = sample_ticks_by_round.get(round_num, [])
            insertion = bisect.bisect_left(available_ticks, contact_tick)
            candidates = available_ticks[
                max(0, insertion - 1): min(len(available_ticks), insertion + 2)
            ]
            nearest_tick = (
                min(candidates, key=lambda value: abs(value - contact_tick))
                if candidates
                else None
            )
            tick_rows = (
                samples_by_round_tick.get((round_num, nearest_tick), [])
                if nearest_tick is not None
                else []
            )
            player_row = next(
                (
                    row for row in tick_rows
                    if str(row["steamid"]) == steamid
                ),
                None,
            )
            teammate_row = next(
                (
                    row for row in tick_rows
                    if str(row["steamid"]) == teammate_id
                ),
                None,
            )
            if (
                player_row is not None
                and teammate_row is not None
                and abs(int(contact_tick) - int(player_row["tick"]))
                <= 2 * tick_rate
                and (
                    player_row["health"] is None
                    or int(player_row["health"]) > 0
                )
            ):
                support_eligible += 1
                support_distance = _distance(
                    player_row["x"],
                    player_row["y"],
                    teammate_row["x"],
                    teammate_row["y"],
                )
                if support_distance is not None:
                    contact_id = str(contact_event["evidence_id"])
                    round_evidence_ids.append(contact_id)
                    support_evidence_ids.append(contact_id)
                    evidence[contact_id] = {
                        "evidence_id": contact_id,
                        "type": "teammate_contact_context",
                        "round_num": round_num,
                        "tick": contact_tick,
                        "distance": support_distance,
                        "summary": (
                            f"队友首次战斗接触时，玩家距离约 "
                            f"{support_distance:.0f} 世界坐标单位"
                        ),
                    }
                if (
                    support_distance is not None
                    and support_distance <= SUPPORT_DISTANCE
                ):
                    support_nearby += 1
                    lookahead = contact_tick + int(
                        tick_rate * SUPPORT_LOOKAHEAD_SECONDS
                    )
                    support_responded = any(
                        row["event_type"] in {"damage", "kill"}
                        and row["actor_steamid"] == steamid
                        and contact_tick <= int(row["tick"]) <= lookahead
                        for row in visible_events
                    )
                    if support_responded:
                        support_responses += 1

        match_kills += len(kills)
        match_deaths += len(deaths)
        match_assists += len(assists)
        opening_contacts += int(opening_contact)
        opening_kills += int(opening_kill)
        opening_deaths += int(opening_death)

        team_economy = (
            economy_by_round_side.get((round_num, side))
            if side is not None
            else None
        )
        positive_components = {
            "kills": len(kills) * 0.8,
            "assists": len(assists) * 0.4,
            "opening_kill": 2.0 if opening_kill else 0.0,
            "survived": 0.4 if survived else 0.0,
            "team_win": 0.5
            if score_states[round_num].get("team_won") is True
            else 0.0,
            "support_nearby": 0.3 if support_distance is not None
            and support_distance <= SUPPORT_DISTANCE
            else 0.0,
            "utility_effect": min(sum(round_utility.values()) * 0.15, 0.45),
        }
        negative_components = {
            "opening_death": 2.0 if opening_death else 0.0,
            "death_without_kill": max(len(deaths) - len(kills), 0) * 0.6,
            "team_loss": 0.4
            if score_states[round_num].get("team_won") is False
            else 0.0,
        }
        positive_score = sum(positive_components.values())
        problem_score = sum(negative_components.values())
        narrative_evidence_ids = list(dict.fromkeys(decision_evidence_ids))
        teammate_death_contexts = _build_teammate_death_contexts(
            round_num=round_num,
            steamid=steamid,
            side=side,
            tick_rate=tick_rate,
            freeze_end=freeze_end,
            visible_events=visible_events,
            samples_by_tick=samples_by_round_tick,
            sample_ticks=sample_ticks_by_round.get(round_num, []),
            evidence=evidence,
        )
        for context in teammate_death_contexts:
            narrative_evidence_ids.extend(context["evidence_ids"])
        narrative = _build_round_narrative(
            round_num=round_num,
            steamid=steamid,
            tick_rate=tick_rate,
            freeze_end=freeze_end,
            team_won=score_states[round_num].get("team_won"),
            visible_events=visible_events,
            round_samples=round_samples,
            first_exit=first_exit,
            early_sequence=early_sequence,
            kills=kills,
            deaths=deaths,
            survived=survived,
            support_distance=support_distance,
            support_responded=support_responded,
            utility_events=dict(round_utility),
            evidence_ids=narrative_evidence_ids,
            teammate_death_contexts=teammate_death_contexts,
        )
        round_facts.append(
            {
                "round_num": round_num,
                "round_evidence_id": round_evidence_id,
                "start_tick": start_tick,
                "freeze_end_tick": freeze_end,
                "end_tick": end_tick,
                "selected_side": side,
                "team_won": score_states[round_num].get("team_won"),
                "game_state": score_states[round_num]["game_state"],
                "score_before": score_states[round_num]["score_before"],
                "economy": {
                    "equipment_value": team_economy["equipment_value"]
                    if team_economy
                    else None,
                    "buy_type": team_economy["buy_type"]
                    if team_economy
                    else None,
                },
                "kills": len(kills),
                "deaths": len(deaths),
                "assists": len(assists),
                "opening_contact": opening_contact,
                "opening_kill": opening_kill,
                "opening_death": opening_death,
                "survived": survived,
                "first_exit_place": first_exit,
                "early_route": early_sequence,
                "nearest_teammate_distance_median": median(round_distances)
                if round_distances
                else None,
                "support_distance": support_distance,
                "support_responded_within_5s": support_responded,
                "utility_events": dict(round_utility),
                "positive_components": positive_components,
                "problem_components": negative_components,
                "excellent_score": positive_score,
                "problem_score": problem_score,
                "impact_score": positive_score - problem_score,
                "evidence_ids": list(dict.fromkeys(round_evidence_ids)),
                "decision_evidence_ids": list(
                    dict.fromkeys(decision_evidence_ids)
                ),
                "narrative": narrative,
                "teammate_death_contexts": teammate_death_contexts,
            }
        )

    rounds_played = len(player_side_by_round)
    metrics = [
        _metric(
            "kills",
            "击杀",
            match_kills,
            unit="次",
            sample_size=rounds_played,
            evidence_ids=kill_evidence_ids,
        ),
        _metric(
            "deaths",
            "死亡",
            match_deaths,
            unit="次",
            sample_size=rounds_played,
            evidence_ids=death_evidence_ids,
        ),
        _metric(
            "assists",
            "助攻",
            match_assists,
            unit="次",
            sample_size=rounds_played,
            evidence_ids=assist_evidence_ids,
        ),
        _metric(
            "opening_contact_rate",
            "首轮交火参与率",
            _ratio(opening_contacts, rounds_played),
            unit="比例",
            sample_size=rounds_played,
            confidence=min(1.0, rounds_played / 10),
            evidence_ids=opening_evidence_ids,
            definition=(
                "每回合第一条有效伤害事件涉及该玩家的回合比例；"
                "同 tick 多事件时顺序存在细微歧义。"
            ),
        ),
        _metric(
            "opening_kills",
            "每回合首杀次数",
            opening_kills,
            unit="次",
            sample_size=rounds_played,
            evidence_ids=opening_evidence_ids,
        ),
        _metric(
            "opening_deaths",
            "每回合首死次数",
            opening_deaths,
            unit="次",
            sample_size=rounds_played,
            evidence_ids=opening_evidence_ids,
        ),
        _metric(
            "nearest_teammate_distance_median",
            "最近存活队友距离中位数",
            median(group_distances) if group_distances else None,
            unit="世界坐标单位",
            sample_size=len(group_distances),
            evidence_ids=route_evidence_ids,
            definition=(
                "行动阶段逐秒采样中，与最近存活队友距离的中位数。"
            ),
        ),
        _metric(
            "near_teammate_ratio",
            "贴近队友采样比例",
            _ratio(
                sum(distance <= NEAR_TEAMMATE_DISTANCE for distance in group_distances),
                len(group_distances),
            ),
            unit="比例",
            sample_size=len(group_distances),
            evidence_ids=route_evidence_ids,
            definition=(
                f"最近存活队友距离不超过 {NEAR_TEAMMATE_DISTANCE:g} "
                "世界坐标单位的行动阶段采样比例。"
            ),
        ),
        _metric(
            "far_teammate_ratio",
            "远离队友采样比例",
            _ratio(
                sum(distance > FAR_TEAMMATE_DISTANCE for distance in group_distances),
                len(group_distances),
            ),
            unit="比例",
            sample_size=len(group_distances),
            evidence_ids=route_evidence_ids,
            definition=(
                f"最近存活队友距离超过 {FAR_TEAMMATE_DISTANCE:g} "
                "世界坐标单位的行动阶段采样比例。"
            ),
        ),
        _metric(
            "support_nearby_rate",
            "队友首次交战时就近比例",
            _ratio(support_nearby, support_eligible),
            unit="比例",
            sample_size=support_eligible,
            confidence=min(1.0, support_eligible / 5),
            evidence_ids=support_evidence_ids,
            definition=(
                "队友首次受伤或造成伤害时，玩家在 3 秒采样容差内的"
                f"距离不超过 {SUPPORT_DISTANCE:g} 的回合比例。"
            ),
        ),
        _metric(
            "support_response_rate",
            "就近后 5 秒内参与战斗比例",
            _ratio(support_responses, support_nearby),
            unit="比例",
            sample_size=support_nearby,
            confidence=min(1.0, support_nearby / 5),
            evidence_ids=support_evidence_ids,
        ),
        _metric(
            "top_places",
            "行动阶段主要活动区域",
            ",".join(place for place, _ in top_place_counter.most_common(5)),
            sample_size=sum(top_place_counter.values()),
            evidence_ids=route_evidence_ids,
            definition="按行动阶段逐秒采样次数排序的前五个地图地点名称。",
        ),
        _metric(
            "first_exit_places",
            "每回合首次离开出生区地点",
            " | ".join(first_exit_places),
            sample_size=len(first_exit_places),
            evidence_ids=route_evidence_ids,
        ),
        _metric(
            "advantage_far_teammate_ratio",
            "领先局远离队友比例",
            _ratio(
                sum(
                    distance > FAR_TEAMMATE_DISTANCE
                    for distance in state_distances["leading"]
                ),
                len(state_distances["leading"]),
            ),
            unit="比例",
            sample_size=len(state_distances["leading"]),
            confidence=min(1.0, len(state_distances["leading"]) / 60),
            evidence_ids=route_evidence_ids,
        ),
        _metric(
            "disadvantage_far_teammate_ratio",
            "落后局远离队友比例",
            _ratio(
                sum(
                    distance > FAR_TEAMMATE_DISTANCE
                    for distance in state_distances["trailing"]
                ),
                len(state_distances["trailing"]),
            ),
            unit="比例",
            sample_size=len(state_distances["trailing"]),
            confidence=min(1.0, len(state_distances["trailing"]) / 60),
            evidence_ids=route_evidence_ids,
        ),
        _metric(
            "clutch_rounds",
            "进入最后存活状态的回合数",
            len({item["round_num"] for item in clutch_rounds}),
            unit="回合",
            sample_size=rounds_played,
            confidence=min(1.0, rounds_played / 10),
            evidence_ids=clutch_evidence_ids,
            definition=(
                "逐秒采样中玩家存活、本方仅剩其一人且至少一名敌人存活的回合数。"
            ),
        ),
        _metric(
            "utility_effect_rounds",
            "产生可观测道具效果的回合数",
            len(utility_rounds),
            unit="回合",
            sample_size=rounds_played,
            evidence_ids=utility_evidence_ids,
        ),
        _metric(
            "utility_purchases",
            "道具购买次数",
            json.dumps(
                {
                    key: item_purchase_totals.get(key, 0)
                    for key in [
                        "flashbang",
                        "smokegrenade",
                        "hegrenade",
                        "molotov",
                        "incgrenade",
                    ]
                },
                ensure_ascii=False,
            ),
            sample_size=sum(item_purchase_totals.values()),
            evidence_ids=purchase_evidence_ids,
            definition="由购买事件统计；购买不等于实际投掷。",
        ),
        _metric(
            "utility_effects",
            "可观测道具效果",
            json.dumps(dict(utility_totals), ensure_ascii=False),
            sample_size=sum(utility_totals.values()),
            evidence_ids=utility_evidence_ids,
            definition=(
                "包括烟雾、燃烧、闪光致盲及手雷/燃烧伤害事件；"
                "缺失零效果投掷。"
            ),
        ),
    ]

    excellent_round = max(
        round_facts,
        key=lambda item: (item["excellent_score"], -item["problem_score"]),
        default=None,
    )
    problem_round = max(
        round_facts,
        key=lambda item: (item["problem_score"], -item["excellent_score"]),
        default=None,
    )
    impact_round = max(
        round_facts,
        key=lambda item: abs(item["impact_score"]),
        default=None,
    )

    score_by_side = Counter(str(row["winner_side"]) for row in rounds)
    from cs2_review.tactical_patterns import identify_tactical_patterns

    tactical_patterns = identify_tactical_patterns(
        map_name=str(analysis["map_name"]),
        rounds=round_facts,
        metrics=metrics,
        clutch_rounds=clutch_rounds,
    )
    return {
        "schema_version": "1.0",
        "rule_version": RULE_VERSION,
        "match": {
            "analysis_id": str(analysis["analysis_id"]),
            "map_name": analysis["map_name"],
            "round_count": len(rounds),
            "tick_rate": tick_rate,
            "score": {
                "terrorist": score_by_side["terrorist"],
                "counter-terrorist": score_by_side["counter-terrorist"],
            },
        },
        "player": {
            "steamid": steamid,
            "name": player["current_name"],
            "starting_side": player["starting_side"],
        },
        "metrics": metrics,
        "rounds": round_facts,
        "key_rounds": {
            "excellent": excellent_round,
            "problem": problem_round,
            "high_impact": impact_round,
            "clutches": clutch_rounds,
        },
        "tactical_patterns": tactical_patterns,
        "evidence": list(evidence.values()),
        "analysis_limits": [
            "行为结论来自位置、事件和统计规则，不能还原玩家真实心理。",
            "后手闪现、无效投掷等零效果行为可能无法从当前字段完整识别。",
            "同一 tick 的多事件先后顺序可能无法唯一确定。",
            "单场数据只能描述本场倾向，不能代表长期稳定习惯。",
        ],
    }


def _persist_metrics(
    connection: sqlite3.Connection,
    bundle: dict[str, Any],
) -> None:
    analysis_id = bundle["match"]["analysis_id"]
    steamid = bundle["player"]["steamid"]
    rule_version = bundle["rule_version"]

    connection.execute(
        """
        DELETE FROM round_player_metric
        WHERE analysis_id = ? AND steamid = ? AND rule_version = ?
        """,
        (analysis_id, steamid, rule_version),
    )
    connection.execute(
        """
        DELETE FROM match_player_metric
        WHERE analysis_id = ? AND steamid = ? AND rule_version = ?
        """,
        (analysis_id, steamid, rule_version),
    )
    connection.execute(
        """
        DELETE FROM key_round
        WHERE analysis_id = ? AND steamid = ? AND rule_version = ?
        """,
        (analysis_id, steamid, rule_version),
    )

    connection.executemany(
        """
        INSERT INTO match_player_metric (
            analysis_id, steamid, metric_key, value_number, value_text, unit,
            sample_size, confidence, rule_version, evidence_ids_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                analysis_id,
                steamid,
                metric["key"],
                metric["value"]
                if isinstance(metric["value"], (int, float))
                else None,
                metric["value"]
                if not isinstance(metric["value"], (int, float))
                else None,
                metric["unit"],
                metric["sample_size"],
                metric["confidence"],
                rule_version,
                json.dumps(metric["evidence_ids"], ensure_ascii=False),
            )
            for metric in bundle["metrics"]
        ],
    )

    round_rows = []
    for round_fact in bundle["rounds"]:
        for key in [
            "kills",
            "deaths",
            "assists",
            "opening_contact",
            "opening_kill",
            "opening_death",
            "survived",
            "nearest_teammate_distance_median",
            "support_distance",
            "excellent_score",
            "problem_score",
            "impact_score",
        ]:
            value = round_fact[key]
            round_rows.append(
                (
                    analysis_id,
                    round_fact["round_num"],
                    steamid,
                    key,
                    float(value) if isinstance(value, (int, float, bool)) else None,
                    str(value) if isinstance(value, str) else None,
                    None,
                    1,
                    None,
                    rule_version,
                    json.dumps(round_fact["evidence_ids"], ensure_ascii=False),
                )
            )
    connection.executemany(
        """
        INSERT INTO round_player_metric (
            analysis_id, round_num, steamid, metric_key, value_number,
            value_text, unit, sample_size, confidence, rule_version,
            evidence_ids_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        round_rows,
    )

    for category in ["excellent", "problem", "high_impact"]:
        round_fact = bundle["key_rounds"].get(category)
        if not round_fact:
            continue
        if category == "problem":
            score = round_fact["problem_score"]
            rationale = (
                f"问题复盘候选：首死={round_fact['opening_death']}，"
                f"死亡={round_fact['deaths']}，击杀={round_fact['kills']}"
            )
            components = round_fact["problem_components"]
        elif category == "high_impact":
            score = abs(round_fact["impact_score"])
            rationale = (
                f"回合影响分数={round_fact['impact_score']:.2f}，"
                f"队伍获胜={round_fact['team_won']}"
            )
            components = {
                "positive": round_fact["positive_components"],
                "negative": round_fact["problem_components"],
            }
        else:
            score = round_fact["excellent_score"]
            rationale = (
                f"优秀表现候选：击杀={round_fact['kills']}，"
                f"首杀={round_fact['opening_kill']}，"
                f"存活={round_fact['survived']}"
            )
            components = round_fact["positive_components"]
        connection.execute(
            """
            INSERT INTO key_round (
                analysis_id, steamid, round_num, category, rank_score,
                rationale, score_components_json, evidence_ids_json,
                rule_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                analysis_id,
                steamid,
                round_fact["round_num"],
                category,
                score,
                rationale,
                json.dumps(components, ensure_ascii=False),
                json.dumps(round_fact["evidence_ids"], ensure_ascii=False),
                rule_version,
            ),
        )

    connection.execute(
        "UPDATE analysis SET status = 'analyzed' WHERE analysis_id = ?",
        (analysis_id,),
    )


def analyze_player(
    database_path: Path | str,
    *,
    steamid: str | None = None,
    player_name: str | None = None,
) -> dict[str, Any]:
    connection = _connect(database_path)
    try:
        analysis = connection.execute("SELECT * FROM analysis").fetchone()
        if analysis is None:
            raise ValueError("No analysis record exists in the database")

        if steamid is None and player_name is None:
            raise ValueError("Either steamid or player_name is required")
        if steamid is not None:
            player = connection.execute(
                """
                SELECT * FROM player
                WHERE analysis_id = ? AND steamid = ? AND is_recorder = 0
                """,
                (analysis["analysis_id"], steamid),
            ).fetchone()
        else:
            matches = connection.execute(
                """
                SELECT * FROM player
                WHERE analysis_id = ? AND current_name = ? AND is_recorder = 0
                """,
                (analysis["analysis_id"], player_name),
            ).fetchall()
            if len(matches) != 1:
                raise ValueError(
                    f"Player name matched {len(matches)} records; use Steam ID"
                )
            player = matches[0]
        if player is None:
            raise ValueError("Selected player does not exist in this analysis")

        bundle = _build_metrics(
            connection=connection,
            analysis=analysis,
            player=player,
        )
        with connection:
            _persist_metrics(connection, bundle)
        return bundle
    finally:
        connection.close()

