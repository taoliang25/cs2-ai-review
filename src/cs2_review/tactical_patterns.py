"""Explainable tactical-pattern labels derived from computed round facts."""

from __future__ import annotations

from collections import Counter
from typing import Any

PATTERN_RULE_VERSION = "tactical-rules-v0.2"

# These are project-defined map-control groups, not authoritative game labels.
# Unlisted maps still receive route labels using the parser's place names.
MAP_ZONES: dict[str, dict[str, set[str]]] = {
    "de_mirage": {
        "A": {
            "BombsiteA",
            "PalaceInterior",
            "PalaceAlley",
            "Catwalk",
            "Jungle",
            "Connector",
            "Stairs",
            "SnipersNest",
            "Ladder",
            "Truck",
        },
        "B": {
            "BombsiteB",
            "Apartments",
            "Underpass",
            "Shop",
            "BackAlley",
            "House",
            "SideAlley",
        },
        "MID": {"Middle", "TopofMid", "TRamp", "Scaffolding"},
    }
}


def classify_place(map_name: str, place_name: str | None) -> str | None:
    if not place_name:
        return None
    if place_name in {"BombsiteA", "BombsiteB"}:
        return place_name[-1]
    for zone, places in MAP_ZONES.get(map_name, {}).items():
        if place_name in places:
            return zone
    return None


def _pattern(
    key: str,
    label: str,
    rationale: str,
    evidence_ids: list[str],
    *,
    confidence: float,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "rationale": rationale,
        "evidence_ids": list(dict.fromkeys(evidence_ids)),
        "confidence": confidence,
        "rule_version": PATTERN_RULE_VERSION,
    }


def identify_tactical_patterns(
    *,
    map_name: str,
    rounds: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
    clutch_rounds: list[dict[str, Any]],
) -> dict[str, Any]:
    metric_map = {metric["key"]: metric for metric in metrics}
    clutch_by_round = {int(item["round_num"]) for item in clutch_rounds}

    zone_counter: Counter[str] = Counter()
    first_exit_counter: Counter[str] = Counter()
    pattern_counter: Counter[str] = Counter()
    enriched_rounds = []

    for round_fact in rounds:
        patterns = []
        route = [
            str(place)
            for place in round_fact.get("early_route", [])
            if place
        ]
        evidence_ids = list(round_fact.get("evidence_ids", []))
        if route:
            first_exit = route[0]
            first_exit_counter[first_exit] += 1
            patterns.append(
                _pattern(
                    f"early_place_{first_exit}",
                    f"首先进入 {first_exit}",
                    f"前 15 秒首个非出生区地点为 {first_exit}",
                    evidence_ids,
                    confidence=0.85,
                )
            )
            zones = [
                zone
                for place in route
                if (zone := classify_place(map_name, place)) is not None
            ]
            zones = list(dict.fromkeys(zones))
            if zones:
                zone_counter[zones[0]] += 1
                patterns.append(
                    _pattern(
                        f"early_zone_{zones[0]}",
                        f"早期进入 {zones[0]} 区",
                        f"前 15 秒首个可映射区域为 {zones[0]}",
                        evidence_ids,
                        confidence=0.7,
                    )
                )
            if len(zones) >= 2:
                patterns.append(
                    _pattern(
                        f"route_{zones[0]}_to_{zones[1]}",
                        f"{zones[0]} 到 {zones[1]} 的早期转移",
                        "前 15 秒观察到的区域序列为 "
                        + " → ".join(zones),
                        evidence_ids,
                        confidence=0.6,
                    )
                )

        distance = round_fact.get("nearest_teammate_distance_median")
        if isinstance(distance, (int, float)):
            if distance <= 500:
                patterns.append(
                    _pattern(
                        "near_teammate",
                        "与队友保持较近距离",
                        f"最近存活队友距离中位数约 {distance:.0f}",
                        evidence_ids,
                        confidence=0.7,
                    )
                )
            elif distance > 800:
                patterns.append(
                    _pattern(
                        "far_teammate",
                        "远端独立行动",
                        f"最近存活队友距离中位数约 {distance:.0f}",
                        evidence_ids,
                        confidence=0.7,
                    )
                )
            else:
                patterns.append(
                    _pattern(
                        "mixed_teammate_distance",
                        "与队友距离处于过渡区间",
                        f"最近存活队友距离中位数约 {distance:.0f}",
                        evidence_ids,
                        confidence=0.55,
                    )
                )

        if round_fact.get("opening_kill"):
            patterns.append(
                _pattern(
                    "opening_kill",
                    "取得每回合首杀",
                    "该回合首条击杀由目标玩家完成",
                    round_fact.get("decision_evidence_ids", []),
                    confidence=0.9,
                )
            )
        elif round_fact.get("opening_death"):
            patterns.append(
                _pattern(
                    "opening_death",
                    "出现每回合首死",
                    "该回合首条击杀的受害者为目标玩家",
                    round_fact.get("decision_evidence_ids", []),
                    confidence=0.9,
                )
            )
        elif round_fact.get("opening_contact"):
            patterns.append(
                _pattern(
                    "opening_contact",
                    "参与每回合首轮交火",
                    "每回合第一条有效伤害事件涉及目标玩家",
                    round_fact.get("decision_evidence_ids", []),
                    confidence=0.75,
                )
            )

        support_distance = round_fact.get("support_distance")
        if (
            isinstance(support_distance, (int, float))
            and support_distance <= 800
        ):
            key = (
                "support_response"
                if round_fact.get("support_responded_within_5s")
                else "support_nearby_no_response"
            )
            label = (
                "队友接敌后就近响应"
                if round_fact.get("support_responded_within_5s")
                else "队友接敌时就近但未立即响应"
            )
            patterns.append(
                _pattern(
                    key,
                    label,
                    f"队友首次交战时距离约 {support_distance:.0f}",
                    round_fact.get("evidence_ids", []),
                    confidence=0.65,
                )
            )

        if round_fact.get("utility_events"):
            patterns.append(
                _pattern(
                    "observable_utility",
                    "产生可观测道具效果",
                    f"该回合道具效果为 {round_fact['utility_events']}",
                    round_fact.get("evidence_ids", []),
                    confidence=0.75,
                )
            )

        if int(round_fact["round_num"]) in clutch_by_round:
            patterns.append(
                _pattern(
                    "last_alive",
                    "进入最后存活状态",
                    "逐秒采样中玩家为本方唯一存活成员",
                    round_fact.get("evidence_ids", []),
                    confidence=0.8,
                )
            )

        for pattern in patterns:
            pattern_counter[pattern["key"]] += 1
        enriched_rounds.append(
            {
                "round_num": round_fact["round_num"],
                "patterns": patterns,
            }
        )

    route_total = sum(first_exit_counter.values())
    dominant_route = (
        first_exit_counter.most_common(1)[0][0]
        if first_exit_counter
        else None
    )
    zone_coverage = (
        sum(zone_counter.values()) / route_total if route_total else 0.0
    )
    dominant_zone = (
        zone_counter.most_common(1)[0][0]
        if zone_counter and zone_coverage >= 0.5
        else None
    )
    return {
        "rule_version": PATTERN_RULE_VERSION,
        "round_patterns": enriched_rounds,
        "summary": {
            "dominant_first_exit": dominant_route,
            "dominant_first_exit_rate": (
                first_exit_counter[dominant_route] / route_total
                if dominant_route and route_total
                else None
            ),
            "dominant_zone": dominant_zone,
            "dominant_zone_rate": (
                zone_counter[dominant_zone] / route_total
                if dominant_zone and route_total
                else None
            ),
            "zone_coverage": zone_coverage,
            "pattern_counts": dict(pattern_counter),
            "route_distribution": dict(first_exit_counter),
            "zone_distribution": dict(zone_counter),
            "supporting_metrics": {
                key: metric_map.get(key, {}).get("value")
                for key in [
                    "opening_contact_rate",
                    "near_teammate_ratio",
                    "far_teammate_ratio",
                    "support_nearby_rate",
                ]
            },
        },
        "limitations": [
            "模式由位置、事件和距离规则识别，不等同于玩家真实战术意图。",
            "区域映射属于项目规则资产，未覆盖的地图回退为原始地点名称。",
            "单场模式频率只能描述本场倾向。",
        ],
    }

