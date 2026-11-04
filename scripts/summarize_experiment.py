"""Build a compact Markdown summary from a CS2 experiment JSON result."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

SUMMARY_METRICS = [
    ("kills", "击杀"),
    ("deaths", "死亡"),
    ("opening_contact_rate", "首轮交火参与率"),
    ("near_teammate_ratio", "贴近队友比例"),
    ("far_teammate_ratio", "远离队友比例"),
    ("support_nearby_rate", "队友接敌时就近比例"),
    ("support_response_rate", "就近后 5 秒响应率"),
    ("clutch_rounds", "最后存活回合数"),
    ("utility_effect_rounds", "可观测道具效果回合数"),
]


def _failures(demo: dict[str, Any]) -> list[str]:
    return [
        check["name"]
        for check in demo["checks"]
        if check["status"] != "pass"
    ]


def _metric_stats(
    experiment: dict[str, Any],
    demo_indices: set[int],
) -> list[dict[str, Any]]:
    rows: dict[str, list[float]] = defaultdict(list)
    for row in experiment["metrics"]:
        if int(row["demo_index"]) not in demo_indices:
            continue
        try:
            value = float(row["value"])
        except (TypeError, ValueError):
            continue
        rows[str(row["metric_key"])].append(value)

    result = []
    for key, label in SUMMARY_METRICS:
        values = rows.get(key, [])
        if not values:
            continue
        result.append(
            {
                "key": key,
                "label": label,
                "n": len(values),
                "mean": statistics.mean(values),
                "median": statistics.median(values),
                "min": min(values),
                "max": max(values),
            }
        )
    return result


def build_summary(experiment: dict[str, Any]) -> str:
    demos = experiment["demos"]
    complete = [
        demo for demo in demos if demo.get("regulation_complete")
    ]
    incomplete = [
        demo for demo in demos if not demo.get("regulation_complete")
    ]
    complete_indices = {
        int(demo["demo_index"]) for demo in complete
    }
    complete_stats = _metric_stats(experiment, complete_indices)

    lines = [
        "# CS2 Demo 实验汇总",
        "",
        f"- 实验运行：`{experiment['run_id']}`",
        f"- Python：`{experiment['environment']['python']}`",
        f"- Awpy：`{experiment['environment']['awpy']}`",
        f"- demoparser2：`{experiment['environment']['demoparser2']}`",
        f"- Demo 数量：{experiment['demo_count']}",
        f"- 达到常规完整终局：{len(complete)}",
        f"- 全部唯一参赛玩家："
        f"{experiment.get('participant_counts', {}).get('all_unique', '未记录')}",
        f"- 完整对局唯一参赛玩家："
        f"{experiment.get('participant_counts', {}).get('complete_unique', '未记录')}",
        "",
        "> 本文件是真实运行的描述性汇总，不是战术识别准确率。",
        "",
        "## 1. 每场数据质量",
        "",
        "| 地图 | 回合 | 比赛结束 | 常规终局 | 玩家 | 位置采样 | 解析秒数 | 质量警告 |",
        "|---|---:|:---:|:---:|---:|---:|---:|---|",
    ]
    for demo in demos:
        warnings = ", ".join(_failures(demo)) or "无"
        lines.append(
            f"| {demo['map_name']} | {demo['round_count']} | "
            f"{'是' if demo['has_match_end'] else '否'} | "
            f"{'是' if demo['regulation_complete'] else '否'} | "
            f"{demo['player_count']} | {demo['tick_sample_count']} | "
            f"{demo['parse_seconds']:.2f} | {warnings} |"
        )

    lines.extend(
        [
            "",
            "## 2. 汇总",
            "",
            f"- 覆盖地图："
            f"{', '.join(sorted({demo['map_name'] for demo in demos}))}。",
            f"- 选手-对局记录："
            f"{sum(int(demo['player_count']) for demo in demos)}。",
            f"- 常规完整终局地图："
            f"{', '.join(sorted({demo['map_name'] for demo in complete})) or '无'}。",
            f"- 片段或提前结束样本：{len(incomplete)}。",
            "",
            "## 3. 完整对局的玩家指标分布",
            "",
            "| 指标 | 样本数 | 均值 | 中位数 | 最小值 | 最大值 |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for item in complete_stats:
        lines.append(
            f"| {item['label']} | {item['n']} | {item['mean']:.3f} | "
            f"{item['median']:.3f} | {item['min']:.3f} | "
            f"{item['max']:.3f} |"
        )

    lines.extend(
        [
            "",
            "## 4. 解释边界",
            "",
            "- 统计单位是玩家，但玩家来自较少的完整 Demo，不能当作总体分布。",
            "- 职业赛事选手与普通玩家存在明显水平差异，不能代表目标用户群体。",
            "- 没有人工行为标签，因此没有分类准确率。",
            "- 片段可以用来说明解析兼容性，不应与完整对局混合做比赛结局分析。",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize an experiment JSON.")
    parser.add_argument("experiment", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        experiment = json.loads(args.experiment.read_text(encoding="utf-8"))
        summary = build_summary(experiment)
        output = (
            args.output
            if args.output is not None
            else args.experiment.with_name(
                f"{args.experiment.stem}_summary.md"
            )
        )
        output.write_text(summary, encoding="utf-8")
    except Exception as exc:
        print(f"Summary failed: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

