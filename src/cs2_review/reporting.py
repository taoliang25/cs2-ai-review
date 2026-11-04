"""Deterministic report providers for evidence-backed CS2 reviews."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ReportDraft:
    provider: str
    markdown: str
    structured: dict[str, Any]
    provider_model: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ReportProvider(Protocol):
    name: str

    def generate(self, fact_bundle: dict[str, Any]) -> ReportDraft:
        ...


def _metric_map(bundle: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["key"]: item for item in bundle["metrics"]}


def _fmt_percent(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "证据不足"
    return f"{value * 100:.0f}%"


def _fmt_number(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "无"
    return f"{value:.0f}" if float(value).is_integer() else f"{value:.2f}"


def _round_line(round_fact: dict[str, Any]) -> str:
    result = (
        "本队获胜"
        if round_fact.get("team_won") is True
        else "本队失利"
        if round_fact.get("team_won") is False
        else "结果未知"
    )
    route = " → ".join(round_fact.get("early_route") or [])
    opening = (
        "首杀"
        if round_fact.get("opening_kill")
        else "首死"
        if round_fact.get("opening_death")
        else "参与首轮交火"
        if round_fact.get("opening_contact")
        else "未参与首轮交火"
    )
    return (
        f"- 第 {round_fact['round_num']} 回合：{result}，"
        f"K/D/A={round_fact['kills']}/{round_fact['deaths']}/"
        f"{round_fact['assists']}，{opening}，"
        f"前 15 秒路线：{route or '采样不足'}。"
    )


def _key_round_section(
    title: str,
    round_fact: dict[str, Any] | None,
    category: str,
) -> list[str]:
    if not round_fact:
        return [f"### {title}", "", "本场没有足够证据生成该类型回合分析。", ""]

    narrative = round_fact.get("narrative", {})
    narrative_summary = narrative.get("summary", "")
    narrative_impact = "；".join(narrative.get("impact", []))
    if category == "problem":
        explanation = (
            f"系统将该回合列为优先复盘候选。本队结果："
            f"{'获胜' if round_fact.get('team_won') else '失利'}；"
            f"玩家死亡 {round_fact['deaths']} 次，"
            f"首死={round_fact['opening_death']}。"
            "这只能说明该回合存在可继续检查的决策节点，"
            "不能单独证明玩家的选择就是失利原因。"
        )
        alternatives = " ".join(narrative.get("alternatives", [])) or (
            "回看首次不利交战时，玩家是否可以保持更安全的距离、"
            "等待队友形成交叉火力，或优先保留人数优势。"
        )
    elif category == "high_impact":
        explanation = (
            f"该回合对局势变化较明显：玩家取得 "
            f"{round_fact['kills']} 次击杀，首杀="
            f"{round_fact['opening_kill']}，首死="
            f"{round_fact['opening_death']}。"
        )
        alternatives = " ".join(narrative.get("alternatives", [])) or (
            "复盘时可比较：在取得或失去人数优势后，继续追击、"
            "重新集合和控制关键区域三种选择分别带来的风险。"
        )
    else:
        explanation = (
            f"该回合具有较积极的个体证据："
            f"{round_fact['kills']} 次击杀，"
            f"首杀={round_fact['opening_kill']}，"
            f"存活={round_fact['survived']}。"
        )
        alternatives = " ".join(narrative.get("alternatives", [])) or (
            "复盘时确认该回合的成功是否能复制：例如优势是否来自"
            "队友道具、对手站位或可重复的路径选择。"
        )

    if narrative_summary:
        explanation += f" {narrative_summary}"
    if narrative_impact:
        explanation += f" 可观测影响：{narrative_impact}。"
    cited_ids = round_fact.get(
        "decision_evidence_ids", round_fact["evidence_ids"]
    )
    evidence_text = (
        "、".join(cited_ids[:6])
        if cited_ids
        else "暂无事件证据"
    )
    return [
        f"### {title}：第 {round_fact['round_num']} 回合",
        "",
        explanation,
        "",
        f"**可考虑的备选方案（赛后建议）：** {alternatives}",
        "",
        f"**证据：** {evidence_text}",
        "",
    ]


def _round_detail_section(
    title: str,
    round_fact: dict[str, Any] | None,
) -> list[str]:
    if not round_fact:
        return []
    narrative = round_fact.get("narrative", {})
    lines = [
        f"### {title}：第 {round_fact['round_num']} 回合",
        "",
        f"**回合经过。** {narrative.get('summary', '证据不足')}",
        "",
        "**可观测影响。**",
        "",
        *[
            f"- {item}"
            for item in narrative.get("impact", [])
        ],
        "",
        "**赛后可选方案。**",
        "",
        *[
            f"- {item}"
            for item in narrative.get("alternatives", [])
        ],
        "",
        f"**证据：** "
        + (
            "、".join(narrative.get("evidence_ids", [])[:10])
            or "暂无事件证据"
        ),
        "",
    ]
    death_contexts = round_fact.get("teammate_death_contexts", [])
    if death_contexts:
        lines.extend(
            [
                "**队友阵亡后的位置与可选行动。**",
                "",
            ]
        )
        for context in death_contexts:
            distance = context.get("distance_to_nearest_alive_teammate")
            distance_text = (
                f"约 {distance:.0f}"
                if isinstance(distance, (int, float))
                else "未知"
            )
            lines.append(
                f"- 行动开始后约 "
                f"{context['seconds_since_freeze']:.0f} 秒，队友在 "
                f"{context.get('teammate_death_place') or '未知区域'}阵亡；"
                f"目标玩家当时位于 "
                f"{context.get('player_place') or '未知区域'}，"
                f"最近存活队友位于 "
                f"{context.get('nearest_alive_teammate_place') or '未知区域'}"
                f"（距离 {distance_text}），"
                f"双方存活人数为 {context.get('teammates_alive')} 对 "
                f"{context.get('enemies_alive')}。"
            )
            for suggestion in context.get("suggestions", []):
                lines.append(f"- 可考虑：{suggestion}")
        lines.append("")
    return lines


class TemplateReportProvider:
    """Rule-based fallback that uses only values from the FactBundle."""

    name = "template-v0.2"

    def generate(self, fact_bundle: dict[str, Any]) -> ReportDraft:
        metrics = _metric_map(fact_bundle)
        player = fact_bundle["player"]
        match = fact_bundle["match"]
        key_rounds = fact_bundle["key_rounds"]
        rounds = fact_bundle["rounds"]
        tactical = fact_bundle.get("tactical_patterns", {})
        pattern_summary = tactical.get("summary", {})

        far_ratio = metrics["far_teammate_ratio"]["value"]
        near_ratio = metrics["near_teammate_ratio"]["value"]
        contact_rate = metrics["opening_contact_rate"]["value"]
        support_rate = metrics["support_nearby_rate"]["value"]
        support_response = metrics["support_response_rate"]["value"]
        top_places = metrics["top_places"]["value"]
        first_exits = metrics["first_exit_places"]["value"]
        advantage_far = metrics["advantage_far_teammate_ratio"]["value"]
        disadvantage_far = metrics["disadvantage_far_teammate_ratio"]["value"]
        utility_purchases = json.loads(metrics["utility_purchases"]["value"] or "{}")
        utility_effects = json.loads(metrics["utility_effects"]["value"] or "{}")
        first_exit_counts = Counter(
            part.strip()
            for part in (first_exits or "").split("|")
            if part.strip()
        )
        first_exit_summary = "，".join(
            f"{place} {count} 次"
            for place, count in first_exit_counts.most_common()
        )

        style_parts = []
        if near_ratio is not None and far_ratio is not None:
            if near_ratio >= far_ratio:
                style_parts.append("更多行动阶段时间与队友保持较近距离")
            else:
                style_parts.append("有较明显时间与队友拉开距离")
        if top_places:
            style_parts.append(f"行动区域主要覆盖 {top_places}")
        if pattern_summary.get("dominant_zone"):
            style_parts.append(
                f"早期区域规则更常识别到 "
                f"{pattern_summary['dominant_zone']} 区"
            )
        if contact_rate is not None:
            style_parts.append(
                f"参与每回合首轮交火的比例为 {_fmt_percent(contact_rate)}"
            )
        style = "；".join(style_parts) or "可观测行为证据不足"

        strengths = []
        opening_kills = metrics["opening_kills"]["value"] or 0
        if opening_kills:
            strengths.append(f"完成 {opening_kills} 次每回合首杀")
        if support_response is not None and support_response >= 0.5:
            strengths.append(
                f"队友首次交战且玩家在附近时，有 "
                f"{_fmt_percent(support_response)} 的回合在 5 秒内参与战斗"
            )
        if metrics["clutch_rounds"]["value"]:
            strengths.append(
                f"进入 {metrics['clutch_rounds']['value']} 次最后存活状态"
            )
        if not strengths:
            strengths.append("本场样本尚不足以稳定确认优势")

        issues = []
        if far_ratio is not None and far_ratio >= 0.3:
            issues.append(
                f"行动阶段有 {_fmt_percent(far_ratio)} 的采样与最近存活队友"
                "距离较远，需要区分独立控图与脱节"
            )
        if support_rate is not None and support_rate < 0.35:
            issues.append(
                "队友首次交战时，玩家就近比例偏低，团队衔接值得重点复盘"
            )
        if support_response == 0 and metrics["support_response_rate"]["sample_size"]:
            issues.append(
                "可识别的就近支援样本中，未观察到 5 秒内参与战斗"
            )
        elif (
            isinstance(support_response, (int, float))
            and support_response < 0.3
            and metrics["support_response_rate"]["sample_size"] >= 5
        ):
            issues.append(
                f"就近后 5 秒内参与战斗的比例为 "
                f"{_fmt_percent(support_response)}，响应衔接值得复盘"
            )
        if not issues:
            issues.append("本场没有出现达到当前规则阈值的明确结构性问题")

        trend = "领先与落后局对比样本不足"
        if advantage_far is not None and disadvantage_far is not None:
            trend = (
                f"领先局远离队友比例 {_fmt_percent(advantage_far)}，"
                f"落后局 {_fmt_percent(disadvantage_far)}"
            )

        timeline = [_round_line(item) for item in rounds]
        lines = [
            f"# 《{match['map_name']}》个人战术复盘",
            "",
            f"分析玩家：**{player['name']}**  ",
            f"回合数：{match['round_count']}  ",
            f"规则版本：`{fact_bundle['rule_version']}`  ",
            f"报告来源：`{self.name}`",
            "",
            "> 本报告先计算真实事件与位置指标，再生成解释。"
            "“倾向”属于行为推断，不等于读取玩家真实想法。",
            "",
            "## 1. 本场玩家画像",
            "",
            f"**打法定性。** {style}。",
            "",
            "**可观测优势。**",
            "",
            *[f"- {item}" for item in strengths],
            "",
            "**需要检查的习惯或问题。**",
            "",
            *[f"- {item}" for item in issues],
            "",
            f"**局势差异。** {trend}。",
            "",
            "## 2. 回合时间线",
            "",
            *timeline,
            "",
            "## 3. 关键决策分析",
            "",
            *_key_round_section(
                "优秀回合", key_rounds.get("excellent"), "excellent"
            ),
            *_key_round_section(
                "高影响回合", key_rounds.get("high_impact"), "high_impact"
            ),
            *_key_round_section(
                "优先复盘回合", key_rounds.get("problem"), "problem"
            ),
            "## 4. 单回合复盘",
            "",
            *_round_detail_section(
                "优秀案例", key_rounds.get("excellent")
            ),
            *_round_detail_section(
                "优先复盘案例", key_rounds.get("problem")
            ),
            "## 5. 全场总结与训练建议",
            "",
            "本场最值得检查的三个方向：",
            "",
            f"1. **区域路线：** 首次离开出生区地点分布为 "
            f"{first_exit_summary or '采样不足'}。训练时记录这些选择是否获得信息、"
            "控制或队友支援。",
            f"2. **团队衔接：** 当前背离队友比例为 {_fmt_percent(far_ratio)}，"
            f"队友首次交战时就近比例为 {_fmt_percent(support_rate)}。"
            "建议专门练习在队友接敌前完成换位或交叉火力。",
            f"3. **道具执行：** 购买统计为 {utility_purchases}，"
            f"可观测效果为 {utility_effects}。"
            "建议下一场训练重点记录每次投掷的目的和队友是否利用其空间收益。",
            "",
            "训练建议采用“每次只改一个问题”："
            "连续两三场重点观察同一指标，而不是同时重做所有决策。",
            "",
            "## 6. 证据展示",
            "",
        ]

        evidence = fact_bundle.get("evidence", [])
        evidence_by_id = {
            item["evidence_id"]: item for item in evidence
        }
        report_evidence_ids = []
        for category in ["excellent", "problem", "high_impact"]:
            round_fact = key_rounds.get(category)
            if not round_fact:
                continue
            for evidence_id in round_fact.get(
                "decision_evidence_ids", []
            )[:8]:
                if evidence_id not in report_evidence_ids:
                    report_evidence_ids.append(evidence_id)
        selected_evidence = [
            evidence_by_id[evidence_id]
            for evidence_id in report_evidence_ids
            if evidence_id in evidence_by_id
        ]
        if selected_evidence:
            for item in selected_evidence[:20]:
                lines.append(
                    f"- `{item['evidence_id']}`：{item.get('summary', '')}"
                )
        else:
            lines.append("- 当前没有可引用的事件证据。")

        lines.extend(
            [
                "",
                "## 分析限制",
                "",
                *[
                    f"- {item}"
                    for item in fact_bundle.get("analysis_limits", [])
                ],
            ]
        )

        structured = {
            "provider": self.name,
            "player_profile": {
                "style": style,
                "strengths": strengths,
                "issues": issues,
                "game_state_difference": trend,
            },
            "timeline": rounds,
            "key_rounds": key_rounds,
            "tactical_patterns": tactical,
            "summary": {
                "directions": [
                    "区域路线",
                    "团队衔接",
                    "道具执行",
                ]
            },
            "evidence_ids": [
                item["evidence_id"] for item in selected_evidence
            ],
        }
        return ReportDraft(
            provider=self.name,
            markdown="\n".join(lines).strip() + "\n",
            structured=structured,
        )

