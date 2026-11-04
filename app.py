"""Single-page Streamlit MVP for one-player CS2 demo review."""

from __future__ import annotations

import hashlib
import hmac
import html
import json
import os
import re
import shutil
import sqlite3
import sys
import uuid
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
load_dotenv(PROJECT_ROOT / ".env", override=False)


def _load_streamlit_secrets() -> None:
    keys = [
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_BASE_URL",
        "DEEPSEEK_MODEL",
        "LLM_TIMEOUT_SECONDS",
        "LLM_MAX_TOKENS",
        "APP_REQUIRE_ACCESS",
        "APP_ACCESS_CODE",
        "APP_ENFORCE_USAGE_LIMITS",
    ]
    try:
        secrets = st.secrets
        for key in keys:
            if key not in os.environ and key in secrets:
                os.environ[key] = str(secrets[key])
    except Exception:
        # Local development intentionally can run without Streamlit secrets.
        pass

from cs2_review.importer import (
    DEFAULT_OUTPUT_DIR,
    import_demo,
    sha256_file,
)
from cs2_review.exporters import build_docx, build_pdf
from cs2_review.access import (
    UsageLimitError,
    access_code,
    access_control_required,
    analysis_slot,
    usage_limits_enabled,
)
from cs2_review.metrics import PlayerOption, analyze_player, list_players
from cs2_review.reporting import TemplateReportProvider
from cs2_review.llm_report import (
    LLMReportError,
    OpenAICompatibleReportProvider,
)
from cs2_review.map_callouts import (
    localize_place_name,
    localize_text,
    map_display_name,
)
from cs2_review.report_store import save_report
from cs2_review.visualization import (
    build_economy_figure,
    build_radar_figure,
)

DEMO_DIR = PROJECT_ROOT / "data" / "demo"
SESSION_ROOT = PROJECT_ROOT / "data" / "interim" / "sessions"
PUBLIC_SAMPLE_DEMO = PROJECT_ROOT / "assets" / "demo" / "public_sample.dem"
LOCAL_SAMPLE_DEMO = DEMO_DIR / "research_demoparser_test_demo.dem"
SAMPLE_DEMO = (
    PUBLIC_SAMPLE_DEMO
    if PUBLIC_SAMPLE_DEMO.is_file()
    else LOCAL_SAMPLE_DEMO
)
EVENT_LABELS = {
    "kill": "击杀",
    "damage": "伤害",
    "flash_blind": "闪光致盲",
    "smoke": "烟雾",
    "fire": "燃烧",
    "start_plant": "开始下包",
    "finish_plant": "完成下包",
    "defuse": "拆包",
    "pickup": "拾取炸弹",
    "drop": "丢弃炸弹",
    "item_purchase": "购买",
}


def _inject_global_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
            --cs2-bg: #091018;
            --cs2-panel: #101a24;
            --cs2-panel-2: #142230;
            --cs2-border: #26394b;
            --cs2-text: #f2f6f9;
            --cs2-muted: #91a2b2;
            --cs2-orange: #ff6b35;
            --cs2-cyan: #39c6d6;
            --cs2-green: #46d19a;
            --cs2-yellow: #f2bd57;
            --cs2-red: #ef6b6b;
        }
        html, body, [class*="css"] {
            font-family: "Microsoft YaHei", "PingFang SC", system-ui, sans-serif;
        }
        .stApp {
            background:
                radial-gradient(circle at 8% 0%, rgba(57, 198, 214, 0.08), transparent 30rem),
                radial-gradient(circle at 92% 10%, rgba(255, 107, 53, 0.07), transparent 28rem),
                var(--cs2-bg);
            color: var(--cs2-text);
        }
        [data-testid="stHeader"] {
            background: rgba(9, 16, 24, 0.72);
        }
        .block-container {
            max-width: 1380px;
            padding-top: 2.2rem;
            padding-bottom: 4rem;
        }
        h1, h2, h3, h4 {
            letter-spacing: 0.01em;
        }
        p, label, .stMarkdown {
            color: #d7e0e7;
        }
        [data-testid="stSidebar"] {
            background: #0c151e;
            border-right: 1px solid var(--cs2-border);
        }
        [data-testid="stSidebar"] .block-container {
            padding-top: 1.4rem;
        }
        [data-testid="stVerticalBlockBorderWrapper"] {
            background: linear-gradient(145deg, rgba(20, 34, 48, 0.94), rgba(13, 24, 34, 0.96));
            border: 1px solid var(--cs2-border);
            border-radius: 13px;
        }
        [data-testid="stMetric"] {
            min-height: 118px;
            padding: 14px 15px;
            background: linear-gradient(145deg, #142230, #101a24);
            border: 1px solid var(--cs2-border);
            border-radius: 12px;
        }
        [data-testid="stMetricLabel"] {
            color: var(--cs2-muted);
        }
        [data-testid="stMetricValue"] {
            color: var(--cs2-text);
            font-family: "Bahnschrift", "Microsoft YaHei", sans-serif;
        }
        .stButton > button,
        .stDownloadButton > button,
        [data-testid="stFormSubmitButton"] > button {
            min-height: 2.6rem;
            border-radius: 8px;
            border: 1px solid #355067;
            background: #172838;
            color: var(--cs2-text);
            font-weight: 500;
            transition: border-color 120ms ease, transform 120ms ease;
        }
        .stButton > button:hover,
        .stDownloadButton > button:hover,
        [data-testid="stFormSubmitButton"] > button:hover {
            border-color: var(--cs2-orange);
            color: #fff;
            transform: translateY(-1px);
        }
        .stButton > button[kind="primary"],
        [data-testid="stFormSubmitButton"] > button[kind="primary"] {
            background: var(--cs2-orange);
            border-color: var(--cs2-orange);
            color: #fff;
        }
        [data-baseweb="select"] > div,
        [data-baseweb="input"] > div,
        .stTextInput input,
        .stTextArea textarea {
            background: #111e2a !important;
            border-color: var(--cs2-border) !important;
            color: var(--cs2-text) !important;
        }
        [data-testid="stFileUploaderDropzone"] {
            background: #0e1923;
            border: 1px dashed #3d5b73;
            border-radius: 12px;
        }
        [data-testid="stFileUploaderDropzone"]:hover {
            border-color: var(--cs2-orange);
        }
        [data-testid="stForm"] {
            padding: 1.1rem;
            background: #101a24;
            border: 1px solid var(--cs2-border);
            border-radius: 14px;
        }
        [data-testid="stTabs"] [data-baseweb="tab-list"] {
            gap: 0.25rem;
            padding: 0.28rem;
            background: #101a24;
            border: 1px solid var(--cs2-border);
            border-radius: 10px;
        }
        [data-testid="stTabs"] [data-baseweb="tab"] {
            height: 2.75rem;
            padding: 0 1rem;
            border-radius: 7px;
            color: var(--cs2-muted);
        }
        [data-testid="stTabs"] [aria-selected="true"] {
            background: #273846;
            color: #fff;
        }
        [data-testid="stDataFrame"] {
            border: 1px solid var(--cs2-border);
            border-radius: 10px;
        }
        div[data-testid="stAlert"] {
            border-radius: 10px;
        }
        .cs2-brandbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            padding: 0.9rem 1rem;
            margin-bottom: 1.35rem;
            background: rgba(16, 26, 36, 0.86);
            border: 1px solid var(--cs2-border);
            border-radius: 12px;
        }
        .cs2-brand-lockup {
            display: flex;
            align-items: center;
            gap: 0.7rem;
        }
        .cs2-brand-mark {
            display: grid;
            place-items: center;
            width: 2rem;
            height: 2rem;
            color: var(--cs2-orange);
            background: rgba(255, 107, 53, 0.13);
            border: 1px solid rgba(255, 107, 53, 0.35);
            border-radius: 8px;
            font-size: 1.15rem;
        }
        .cs2-brand-name {
            color: #fff;
            font-family: "Bahnschrift", "Microsoft YaHei", sans-serif;
            font-size: 0.95rem;
            letter-spacing: 0.08em;
        }
        .cs2-brand-note {
            color: var(--cs2-muted);
            font-size: 0.75rem;
        }
        .cs2-step {
            color: var(--cs2-orange);
            font-family: "Bahnschrift", monospace;
            font-size: 0.72rem;
            font-weight: 500;
            letter-spacing: 0.12em;
            text-transform: uppercase;
        }
        .cs2-section-title {
            margin: 0.15rem 0 0.2rem;
            color: var(--cs2-text);
            font-size: 1.55rem;
            font-weight: 500;
            line-height: 1.3;
        }
        .cs2-section-copy {
            margin-bottom: 0.9rem;
            color: var(--cs2-muted);
            font-size: 0.86rem;
        }
        .cs2-hero {
            position: relative;
            display: flex;
            align-items: flex-end;
            justify-content: space-between;
            gap: 1.5rem;
            margin: 0.65rem 0 1rem;
            padding: 1.35rem 1.45rem;
            overflow: hidden;
            background:
                linear-gradient(105deg, rgba(8, 15, 22, 0.92), rgba(17, 34, 47, 0.82)),
                repeating-linear-gradient(135deg, transparent 0 18px, rgba(255,255,255,0.025) 18px 19px);
            border: 1px solid #304658;
            border-radius: 14px;
        }
        .cs2-hero::after {
            content: "TACTICAL REVIEW";
            position: absolute;
            top: 0.7rem;
            right: 1.1rem;
            color: rgba(255,255,255,0.055);
            font-family: "Bahnschrift", sans-serif;
            font-size: 2rem;
            letter-spacing: 0.12em;
            pointer-events: none;
        }
        .cs2-player {
            position: relative;
            z-index: 1;
            display: flex;
            align-items: center;
            gap: 0.9rem;
        }
        .cs2-avatar {
            display: grid;
            place-items: center;
            width: 3.1rem;
            height: 3.1rem;
            color: var(--cs2-cyan);
            background: rgba(57, 198, 214, 0.12);
            border: 1px solid rgba(57, 198, 214, 0.35);
            border-radius: 11px;
            font-family: "Bahnschrift", monospace;
            font-size: 1.15rem;
        }
        .cs2-player h2 {
            margin: 0;
            color: #fff;
            font-size: 2rem;
            font-weight: 500;
        }
        .cs2-tag-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.35rem;
            margin-top: 0.45rem;
        }
        .cs2-pill {
            display: inline-flex;
            align-items: center;
            padding: 0.18rem 0.48rem;
            color: #aab9c6;
            background: rgba(255,255,255,0.045);
            border: 1px solid var(--cs2-border);
            border-radius: 5px;
            font-size: 0.72rem;
        }
        .cs2-pill.cyan {
            color: var(--cs2-cyan);
            background: rgba(57, 198, 214, 0.12);
            border-color: rgba(57, 198, 214, 0.28);
        }
        .cs2-score {
            position: relative;
            z-index: 1;
            min-width: 8.5rem;
            padding-left: 1.2rem;
            text-align: right;
            border-left: 1px solid #354a5d;
        }
        .cs2-score strong {
            color: var(--cs2-text);
            font-family: "Bahnschrift", monospace;
            font-size: 2.3rem;
            font-weight: 500;
        }
        .cs2-score span {
            display: block;
            color: var(--cs2-muted);
            font-size: 0.75rem;
        }
        .cs2-coach-card {
            height: 100%;
            padding: 1rem 1.05rem;
            background:
                linear-gradient(155deg, rgba(57,198,214,0.08), transparent 48%),
                var(--cs2-panel);
            border: 1px solid var(--cs2-border);
            border-radius: 13px;
        }
        .cs2-coach-card h3 {
            margin: 0.25rem 0 0.55rem;
            color: #fff;
            font-size: 1.18rem;
            font-weight: 500;
            line-height: 1.42;
        }
        .cs2-coach-card p {
            color: #bfcbd4;
            font-size: 0.84rem;
        }
        .cs2-coach-kicker {
            color: var(--cs2-cyan);
            font-family: "Bahnschrift", monospace;
            font-size: 0.72rem;
            letter-spacing: 0.1em;
        }
        .cs2-priority-list {
            display: grid;
            gap: 0.45rem;
            margin-top: 0.9rem;
        }
        .cs2-priority-item {
            display: grid;
            grid-template-columns: 1.65rem minmax(0, 1fr);
            gap: 0.5rem;
            padding: 0.6rem;
            background: rgba(255,255,255,0.035);
            border-radius: 7px;
        }
        .cs2-priority-num {
            display: grid;
            place-items: center;
            width: 1.65rem;
            height: 1.65rem;
            color: var(--cs2-yellow);
            background: rgba(242,189,87,0.13);
            border-radius: 5px;
            font-family: "Bahnschrift", monospace;
            font-size: 0.72rem;
        }
        .cs2-priority-item strong {
            display: block;
            color: #eef3f7;
            font-size: 0.8rem;
            font-weight: 500;
        }
        .cs2-priority-item span {
            display: block;
            margin-top: 0.1rem;
            color: var(--cs2-muted);
            font-size: 0.72rem;
        }
        .cs2-panel-title {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.7rem;
            margin: 0.4rem 0 0.55rem;
            color: #edf3f7;
            font-size: 1rem;
            font-weight: 500;
        }
        .cs2-panel-title small {
            color: var(--cs2-muted);
            font-size: 0.72rem;
            font-weight: 400;
        }
        .cs2-report-head {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            margin: 0.7rem 0;
            padding: 0.75rem 0.9rem;
            background: #101a24;
            border: 1px solid var(--cs2-border);
            border-radius: 10px;
        }
        .cs2-report-head strong {
            color: #fff;
            font-weight: 500;
        }
        .cs2-report-head span {
            color: var(--cs2-muted);
            font-size: 0.75rem;
        }
        .cs2-report-section {
            margin: 0.8rem 0 0.3rem;
            padding: 0.7rem 0.85rem;
            color: #fff;
            background: #142230;
            border-left: 3px solid var(--cs2-orange);
            border-radius: 0 8px 8px 0;
            font-size: 1.02rem;
            font-weight: 500;
        }
        .cs2-claim {
            margin: 0.35rem 0;
            padding: 0.65rem 0.8rem;
            background: #0f1a24;
            border: 1px solid #223445;
            border-radius: 8px;
            color: #d7e1e8;
            font-size: 0.84rem;
            line-height: 1.7;
        }
        .cs2-claim.observation {
            border-left: 3px solid var(--cs2-cyan);
        }
        .cs2-claim.inference {
            border-left: 3px solid var(--cs2-yellow);
        }
        .cs2-claim.recommendation {
            border-left: 3px solid var(--cs2-green);
        }
        .cs2-claim-label {
            display: inline-block;
            margin-right: 0.35rem;
            color: var(--cs2-muted);
            font-size: 0.68rem;
        }
        .cs2-round-card {
            padding: 0.9rem 1rem;
            background: linear-gradient(145deg, #142230, #101a24);
            border: 1px solid var(--cs2-border);
            border-radius: 11px;
        }
        .cs2-round-card h3 {
            margin: 0.18rem 0 0.55rem;
            color: #fff;
            font-size: 1.1rem;
            font-weight: 500;
        }
        .cs2-round-card p {
            color: #b7c4ce;
            font-size: 0.82rem;
        }
        .cs2-kicker {
            color: var(--cs2-orange);
            font-family: "Bahnschrift", monospace;
            font-size: 0.7rem;
            letter-spacing: 0.08em;
        }
        @media (max-width: 720px) {
            .block-container {
                padding-left: 1rem;
                padding-right: 1rem;
            }
            .cs2-hero {
                align-items: flex-start;
                flex-direction: column;
            }
            .cs2-score {
                width: 100%;
                padding: 0.7rem 0 0;
                text-align: left;
                border-top: 1px solid #354a5d;
                border-left: 0;
            }
            .cs2-player h2 {
                font-size: 1.55rem;
            }
            .cs2-brand-note {
                display: none;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_brandbar() -> None:
    st.markdown(
        """
        <div class="cs2-brandbar">
          <div class="cs2-brand-lockup">
            <span class="cs2-brand-mark">◎</span>
            <div>
              <div class="cs2-brand-name">CS2 TACTICAL REVIEW</div>
              <div class="cs2-brand-note">单场对局 · 单玩家 · 证据驱动</div>
            </div>
          </div>
          <span class="cs2-pill cyan">行为推断，不读取玩家想法</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_section_intro(
    step: str,
    title: str,
    description: str,
) -> None:
    st.markdown(
        f"""
        <div class="cs2-step">{html.escape(step)}</div>
        <div class="cs2-section-title">{html.escape(title)}</div>
        <div class="cs2-section-copy">{html.escape(description)}</div>
        """,
        unsafe_allow_html=True,
    )


def _metric_value(metric: dict, map_name: str | None = None) -> str:
    value = metric["value"]
    if value is None:
        return "证据不足"
    if metric["unit"] == "比例" and isinstance(value, (int, float)):
        return f"{value * 100:.0f}%"
    if isinstance(value, str):
        return localize_text(map_name, value)
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


def _side_label(side: str | None) -> str:
    return {
        "terrorist": "T 进攻方",
        "counter-terrorist": "CT 防守方",
    }.get(str(side or ""), "阵营未知")


def _render_player_hero(player: dict, match: dict) -> None:
    player_name = html.escape(str(player.get("name") or "未知玩家"))
    map_name = html.escape(map_display_name(match.get("map_name")))
    side = html.escape(_side_label(player.get("starting_side")))
    score = match.get("score", {})
    t_score = html.escape(str(score.get("terrorist", 0)))
    ct_score = html.escape(str(score.get("counter-terrorist", 0)))
    rounds = html.escape(str(match.get("round_count", 0)))
    st.markdown(
        f"""
        <div class="cs2-hero">
          <div class="cs2-player">
            <div class="cs2-avatar">{player_name[:2]}</div>
            <div>
              <h2>{player_name}</h2>
              <div class="cs2-tag-row">
                <span class="cs2-pill cyan">{side}</span>
                <span class="cs2-pill">{map_name}</span>
                <span class="cs2-pill">{rounds} 回合</span>
                <span class="cs2-pill">证据驱动</span>
              </div>
            </div>
          </div>
          <div class="cs2-score">
            <strong>{t_score} : {ct_score}</strong>
            <span>T / CT · 本场比分</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _coach_summary(
    facts: dict,
    metrics: dict[str, dict],
) -> tuple[str, str, list[tuple[str, str]]]:
    support_rate = metrics["support_nearby_rate"]["value"]
    far_ratio = metrics["far_teammate_ratio"]["value"]
    contact_rate = metrics["opening_contact_rate"]["value"]
    opening_kills = metrics["opening_kills"]["value"] or 0
    opening_deaths = metrics["opening_deaths"]["value"] or 0

    strengths: list[str] = []
    if opening_kills:
        strengths.append(f"完成 {opening_kills} 次首杀")
    kills = metrics["kills"]["value"] or 0
    if kills:
        strengths.append(f"本场取得 {kills} 次击杀")

    priorities: list[tuple[str, str]] = []
    if isinstance(support_rate, (int, float)) and support_rate < 0.35:
        priorities.append(
            (
                "支援时机偏晚",
                f"队友接敌时就近比例仅 {support_rate * 100:.0f}%",
            )
        )
    if isinstance(far_ratio, (int, float)) and far_ratio >= 0.3:
        priorities.append(
            (
                "远端行动偏多",
                f"{far_ratio * 100:.0f}% 的位置采样远离最近队友",
            )
        )
    if (
        isinstance(contact_rate, (int, float))
        and contact_rate >= 0.4
        and opening_deaths >= max(1, opening_kills)
    ):
        priorities.append(
            (
                "首轮交火风险偏高",
                "先确认补枪距离或道具保护条件",
            )
        )
    if not priorities:
        priorities.extend(
            [
                ("继续记录路线收益", "比较控图、信息和团队支援的结果"),
                ("固定团队重组习惯", "人数变化后先确认最近队友位置"),
                ("复盘道具使用目的", "检查投掷是否为队友创造空间"),
            ]
        )

    if support_rate is not None and support_rate < 0.35:
        headline = "个人输出有亮点，团队衔接是优先改进方向"
        copy = (
            f"你本场完成 {kills} 次击杀，但队友接敌时就近比例只有 "
            f"{support_rate * 100:.0f}%。下一步优先练习交火前换位，"
            "比继续只追求个人对枪更容易改善回合结果。"
        )
    elif far_ratio is not None and far_ratio >= 0.3:
        headline = "地图覆盖较积极，远端行动需要更好的重组规则"
        copy = (
            f"本场有 {far_ratio * 100:.0f}% 的位置采样远离最近队友。"
            "独立控图本身不是问题，关键是人数变化后能及时说明何时回队。"
        )
    elif strengths:
        headline = "整体执行较连贯，可以把本场成功路径固定下来"
        copy = (
            f"本场优势包括{'、'.join(strengths[:2])}。"
            "继续核对这些结果是否来自可重复的路线、道具和队友配合。"
        )
    else:
        headline = "本场样本有限，先建立可重复的行为基线"
        copy = "建议继续积累同类局面，区分稳定习惯和单回合偶然表现。"
    return headline, copy, priorities[:3]


def _render_coach_summary(facts: dict, metrics: dict[str, dict]) -> None:
    headline, copy, priorities = _coach_summary(facts, metrics)
    priority_html = "".join(
        (
            '<div class="cs2-priority-item">'
            f'<span class="cs2-priority-num">0{index}</span>'
            f"<div><strong>{html.escape(title)}</strong>"
            f"<span>{html.escape(detail)}</span></div></div>"
        )
        for index, (title, detail) in enumerate(priorities, start=1)
    )
    st.markdown(
        f"""
        <div class="cs2-coach-card">
          <div class="cs2-coach-kicker">AI COACH · 本场摘要</div>
          <h3>{html.escape(headline)}</h3>
          <p>{html.escape(copy)}</p>
          <div class="cs2-priority-list">{priority_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _clean_claim_text(text: str) -> str:
    return re.sub(r"\s*（证据：[^）]+）", "", str(text)).strip()


def _render_claim(
    text: str,
    claim_type: str,
    evidence_ids: list[str],
) -> None:
    labels = {
        "observation": "事实",
        "inference": "行为推断",
        "recommendation": "训练建议",
    }
    kind = claim_type if claim_type in labels else "observation"
    st.markdown(
        f"""
        <div class="cs2-claim {kind}">
          <span class="cs2-claim-label">{labels[kind]}</span>
          {html.escape(_clean_claim_text(text))}
        </div>
        """,
        unsafe_allow_html=True,
    )
    if evidence_ids:
        with st.expander(f"查看证据 · {len(evidence_ids)} 条", expanded=False):
            st.code("\n".join(evidence_ids), language=None)


def _render_structured_report(report, facts: dict) -> None:
    structured = report.structured
    sections = structured.get("sections")
    map_name = facts["match"]["map_name"]
    provider_text = report.provider
    if report.provider_model:
        provider_text += f" / {report.provider_model}"
    st.markdown(
        f"""
        <div class="cs2-report-head">
          <strong>AI 教练复盘</strong>
          <span>{html.escape(provider_text)} · 证据已校验</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    headline = structured.get("headline")
    if headline:
        st.markdown(
            f'<div class="cs2-claim recommendation">'
            f'<span class="cs2-claim-label">一句话结论</span>'
            f"{html.escape(str(headline))}</div>",
            unsafe_allow_html=True,
        )

    if isinstance(sections, list) and sections:
        for section in sections:
            title = html.escape(str(section.get("title") or "复盘结论"))
            st.markdown(
                f'<div class="cs2-report-section">{title}</div>',
                unsafe_allow_html=True,
            )
            for claim in section.get("claims", []):
                _render_claim(
                    str(claim.get("text") or ""),
                    str(claim.get("claim_type") or "observation"),
                    [str(item) for item in claim.get("evidence_ids", [])],
                )
        return

    profile = structured.get("profile") or structured.get(
        "player_profile",
        {},
    )
    if profile.get("style"):
        _render_claim(
            localize_text(map_name, str(profile["style"])),
            "inference",
            [],
        )
    if profile.get("strengths"):
        for item in profile["strengths"]:
            _render_claim(
                localize_text(map_name, str(item)),
                "observation",
                [],
            )
    if profile.get("issues"):
        for item in profile["issues"]:
            _render_claim(
                localize_text(map_name, str(item)),
                "recommendation",
                [],
            )
    if profile.get("game_state_difference"):
        _render_claim(
            localize_text(
                map_name,
                str(profile["game_state_difference"]),
            ),
            "inference",
            [],
        )

    for category, title in [
        ("excellent", "表现较好的回合"),
        ("problem", "优先复盘回合"),
        ("high_impact", "高影响回合"),
    ]:
        round_fact = facts["key_rounds"].get(category)
        if not round_fact:
            continue
        narrative = round_fact.get("narrative", {})
        st.markdown(
            f'<div class="cs2-report-section">'
            f"{html.escape(title)} · 第 {round_fact['round_num']} 回合</div>",
            unsafe_allow_html=True,
        )
        if narrative.get("summary"):
            _render_claim(
                localize_text(
                    map_name,
                    str(narrative["summary"]),
                ),
                "observation",
                list(narrative.get("evidence_ids", [])),
            )
        for item in narrative.get("impact", []):
            _render_claim(
                localize_text(map_name, str(item)),
                "inference",
                [],
            )
        for item in narrative.get("alternatives", []):
            _render_claim(
                localize_text(map_name, str(item)),
                "recommendation",
                [],
            )

    st.markdown(
        '<div class="cs2-report-section">本轮优先训练方向</div>',
        unsafe_allow_html=True,
    )
    metrics = {item["key"]: item for item in facts["metrics"]}
    _, _, priorities = _coach_summary(facts, metrics)
    for title, detail in priorities:
        _render_claim(
            f"{title}：{detail}",
            "recommendation",
            [],
        )
    evidence_ids = structured.get("evidence_ids", [])
    if evidence_ids:
        with st.expander(
            f"查看报告证据 · {len(evidence_ids)} 条",
            expanded=False,
        ):
            st.code("\n".join(map(str, evidence_ids)), language=None)


def _session_work_dir() -> Path:
    raw_path = st.session_state.get("session_work_dir")
    if raw_path:
        path = Path(raw_path)
    else:
        path = SESSION_ROOT / uuid.uuid4().hex
        st.session_state["session_work_dir"] = str(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _database_for_hash(demo_hash: str, *, temporary: bool) -> Path:
    parent = _session_work_dir() if temporary else DEFAULT_OUTPUT_DIR
    return parent / f"{demo_hash[:12]}.sqlite"


def _safe_file_stem(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")
    return cleaned[:80] or "player"


def _connect(database_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    return connection


def _get_analysis(database_path: Path) -> sqlite3.Row:
    connection = _connect(database_path)
    try:
        row = connection.execute("SELECT * FROM analysis").fetchone()
    finally:
        connection.close()
    if row is None:
        raise ValueError("数据库中没有对局记录")
    return row


def _set_database(database_path: Path, *, temporary: bool = False) -> None:
    st.session_state["database_path"] = str(database_path.resolve())
    st.session_state.pop("facts", None)
    st.session_state.pop("report", None)
    st.session_state.pop("selected_round", None)
    st.session_state["temporary_database"] = temporary


def _delete_session_database() -> None:
    raw_path = st.session_state.get("database_path")
    if raw_path and st.session_state.get("temporary_database"):
        database_path = Path(raw_path)
        for suffix in ["", "-wal", "-shm"]:
            candidate = Path(str(database_path) + suffix)
            if candidate.exists():
                candidate.unlink()

    raw_work_dir = st.session_state.pop("session_work_dir", None)
    if raw_work_dir:
        work_dir = Path(raw_work_dir).resolve()
        session_root = SESSION_ROOT.resolve()
        if work_dir.parent == session_root and work_dir.exists():
            shutil.rmtree(work_dir, ignore_errors=True)

    st.session_state.pop("database_path", None)
    st.session_state.pop("temporary_database", None)
    st.session_state.pop("processed_upload_id", None)


def _clear_analysis_state() -> None:
    for key in [
        "facts",
        "report",
        "report_warning",
        "selected_steamid",
        "selected_round",
    ]:
        st.session_state.pop(key, None)


def _parse_or_reuse(
    demo_path: Path,
    *,
    temporary: bool = False,
    upload_id: str | None = None,
) -> Path:
    demo_hash = sha256_file(demo_path)
    database_path = _database_for_hash(demo_hash, temporary=temporary)
    if not database_path.exists():
        try:
            with analysis_slot(enabled=usage_limits_enabled()):
                with st.spinner(
                    "正在解析 Demo 并建立临时事实库，首次解析可能需要几十秒……"
                ):
                    import_demo(demo_path, output_path=database_path)
        except UsageLimitError as exc:
            st.error(str(exc))
            st.stop()
    if temporary and demo_path.exists():
        demo_path.unlink()
    if upload_id:
        st.session_state["processed_upload_id"] = upload_id
    _set_database(database_path, temporary=temporary)
    return database_path


def _render_upload() -> Path | None:
    _render_section_intro(
        "STEP 01 · IMPORT",
        "导入一场对局",
        "上传 .dem 文件，系统会建立临时事实库；原始文件在解析完成后立即删除。",
    )
    with st.container(border=True):
        uploaded = st.file_uploader(
            "选择 CS2 常规 5v5 Demo",
            type=["dem"],
            help=(
                "一次只分析一场 .dem。文件大小上限为 1 GB，"
                "上传内容仅用于本次临时分析。"
            ),
        )
        upload_id = None
        if uploaded is not None:
            if uploaded.size > 1024**3:
                st.error("单个 Demo 不能超过 1 GB。")
            else:
                upload_id = str(
                    getattr(
                        uploaded,
                        "file_id",
                        f"{uploaded.name}:{uploaded.size}",
                    )
                )
                already_processed = (
                    st.session_state.get("processed_upload_id") == upload_id
                )
                if not already_processed:
                    work_dir = _session_work_dir()
                    temporary = work_dir / (
                        f".uploading-{uuid.uuid4().hex}.dem"
                    )
                    digest = hashlib.sha256()
                    with temporary.open("wb") as stream:
                        while chunk := uploaded.read(8 * 1024 * 1024):
                            digest.update(chunk)
                            stream.write(chunk)
                    saved = work_dir / (
                        f"upload-{digest.hexdigest()[:12]}.dem"
                    )
                    if saved.exists():
                        temporary.unlink()
                    else:
                        temporary.replace(saved)
                    if st.button("解析这场 Demo", type="primary"):
                        return _parse_or_reuse(
                            saved,
                            temporary=True,
                            upload_id=upload_id,
                        )

        cached_demos = (
            sorted(DEMO_DIR.glob("*.dem"))
            if DEMO_DIR.is_dir()
            else []
        )
        cached_demos = [
            path for path in cached_demos
            if path.resolve() != PUBLIC_SAMPLE_DEMO.resolve()
        ]
        if PUBLIC_SAMPLE_DEMO.is_file():
            cached_demos.insert(0, PUBLIC_SAMPLE_DEMO)
        if cached_demos:
            preferred = next(
                (
                    path for path in cached_demos
                    if path.name == "furia-vs-falcons-m2-nuke.dem"
                ),
                (
                    SAMPLE_DEMO
                    if SAMPLE_DEMO in cached_demos
                    else cached_demos[0]
                ),
            )
            st.divider()
            st.markdown(
                '<div class="cs2-panel-title">'
                "或者载入公开演示样本"
                "<small>无需准备文件</small></div>",
                unsafe_allow_html=True,
            )
            selected_demo = st.selectbox(
                "已缓存验证 Demo",
                cached_demos,
                index=cached_demos.index(preferred),
                format_func=lambda path: path.name,
            )
            st.caption(
                "公开演示用于验证完整流程；自己的 Demo 更能代表个人习惯。"
            )
            if st.button("载入已缓存的测试 Demo"):
                return _parse_or_reuse(selected_demo, temporary=False)
    return None


def _load_event_rows(
    database_path: Path,
    analysis_id: str,
    round_num: int,
) -> pd.DataFrame:
    connection = _connect(database_path)
    try:
        rows = connection.execute(
            """
            SELECT e.evidence_id, e.tick, e.event_type, e.actor_steamid,
                   e.target_steamid, e.weapon, e.payload_json,
                   r.freeze_end_tick, r.start_tick, a.tick_rate
            FROM game_event e
            JOIN round r
              ON r.analysis_id = e.analysis_id
             AND r.round_num = e.round_num
            JOIN analysis a ON a.analysis_id = e.analysis_id
            WHERE e.analysis_id = ? AND e.round_num = ?
              AND e.event_type IN (
                  'kill', 'damage', 'flash_blind', 'smoke', 'fire',
                  'start_plant', 'finish_plant', 'defuse'
              )
            ORDER BY e.tick, e.evidence_id
            """,
            (analysis_id, round_num),
        ).fetchall()
        players = {
            str(row["steamid"]): str(row["current_name"])
            for row in connection.execute(
                "SELECT steamid, current_name FROM player"
            ).fetchall()
        }
    finally:
        connection.close()

    records = []
    for row in rows:
        payload = json.loads(row["payload_json"] or "{}")
        if payload.get("is_post_round"):
            continue
        freeze = row["freeze_end_tick"] or row["start_tick"]
        tick_rate = row["tick_rate"] or 64
        records.append(
            {
                "时间": f"{(int(row['tick']) - int(freeze)) / float(tick_rate):.1f}s",
                "事件": EVENT_LABELS.get(row["event_type"], row["event_type"]),
                "行动者": players.get(str(row["actor_steamid"]), "—"),
                "目标": players.get(str(row["target_steamid"]), "—"),
                "武器/道具": row["weapon"] or "—",
                "证据编号": row["evidence_id"],
            }
        )
    return pd.DataFrame(records)


def _render_analysis(database_path: Path) -> None:
    analysis = _get_analysis(database_path)
    players = list_players(database_path)
    has_match_end = (
        bool(analysis["has_match_end"])
        if "has_match_end" in analysis.keys()
        else None
    )
    regulation_complete = (
        bool(analysis["regulation_complete"])
        if "regulation_complete" in analysis.keys()
        else None
    )
    if has_match_end is False:
        st.warning(
            "该 Demo 未检测到完整比赛结束事件，可能只记录了部分对局。"
            "可以用于开发检查，但不适合作为最终完整比赛证据。"
        )
    elif has_match_end is None:
        st.info("旧数据库未记录比赛完整性字段；重新导入后可自动检查。")
    elif regulation_complete is False:
        st.warning(
            "该对局虽检测到比赛结束，但未达到常规赛目标得分，"
            "可能为投降、片段或非常规模式。"
        )
    if len(players) != 10:
        st.warning(
            f"当前解析到 {len(players)} 名有效玩家。首版预期为常规 5v5，"
            "请确认该 Demo 的来源和模式。"
        )

    with st.sidebar:
        st.markdown("### 分析设置")
        st.markdown(
            f'<span class="cs2-pill cyan">'
            f'{html.escape(map_display_name(analysis["map_name"]))}'
            "</span>",
            unsafe_allow_html=True,
        )
        st.caption(f"Demo 哈希前 12 位：{analysis['demo_sha256'][:12]}")
        st.divider()
        st.markdown("**报告生成方式**")
        deepseek_configured = bool(
            os.getenv("DEEPSEEK_API_KEY") or os.getenv("LLM_API_KEY")
        )
        report_engine = st.selectbox(
            "报告引擎",
            ["DeepSeek 云端", "本地模板"],
            index=0 if deepseek_configured else 1,
            help=(
                "云端模型只接收去标识化统计和事件摘要；"
                "不发送 Demo 文件、玩家名、Steam ID 或原始坐标。"
            ),
        )
        if report_engine == "DeepSeek 云端":
            if deepseek_configured:
                st.caption("已检测到 DeepSeek 密钥环境变量。")
            else:
                st.warning("未配置 DEEPSEEK_API_KEY，将使用模板报告。")
        else:
            st.caption("不联网、不调用模型，报告功能始终可用。")
        if st.session_state.get("temporary_database") and st.button(
            "结束并删除本次分析数据"
        ):
            _delete_session_database()
            _clear_analysis_state()
            st.rerun()
        if access_control_required() and st.button("退出访问"):
            _delete_session_database()
            _clear_analysis_state()
            st.session_state.pop("authenticated", None)
            st.rerun()

    _render_section_intro(
        "STEP 02 · PLAYER",
        "选择主要分析玩家",
        "从真实玩家列表中选择一人，后续画像、回合和证据都只围绕该玩家。",
    )
    labels = {
        (
            f"{player.name}｜{_side_label(player.starting_side)}"
            f"｜{player.steamid}"
        ): player
        for player in players
    }
    with st.container(border=True):
        selected_label = st.selectbox("点击选择玩家", list(labels))
        selected: PlayerOption = labels[selected_label]
        generate_clicked = st.button(
            "生成 AI 画像与复盘",
            type="primary",
        )

    if generate_clicked:
        with st.spinner("正在计算真实事件指标、关键回合和报告……"):
            facts = analyze_player(
                database_path,
                steamid=selected.steamid,
            )
            report_warning = None
            if report_engine != "本地模板":
                try:
                    if report_engine == "DeepSeek 云端":
                        provider = (
                            OpenAICompatibleReportProvider.from_deepseek()
                        )
                    report = provider.generate(facts)
                except LLMReportError as exc:
                    report_warning = f"大模型报告未采用：{exc}"
                    report = TemplateReportProvider().generate(facts)
            else:
                report = TemplateReportProvider().generate(facts)
            try:
                save_report(
                    database_path,
                    fact_bundle=facts,
                    report=report,
                )
            except Exception as exc:
                st.warning(f"报告已生成，但未写入本地报告表：{exc}")
            st.session_state["facts"] = facts
            st.session_state["report"] = report
            st.session_state["report_warning"] = report_warning
            st.session_state["selected_steamid"] = selected.steamid

    facts = st.session_state.get("facts")
    if not facts:
        return
    if facts["player"]["steamid"] != selected.steamid:
        st.info("分析玩家已更改，请点击“生成 AI 画像与复盘”。")
        return

    match = facts["match"]
    player = facts["player"]
    metrics = {item["key"]: item for item in facts["metrics"]}
    report = st.session_state["report"]

    _render_player_hero(player, match)

    tabs = st.tabs(
        ["教练总览", "位置与路线", "关键回合", "单回合复盘", "完整报告"]
    )
    with tabs[0]:
        columns = st.columns(4)
        card_keys = [
            ("kills", "本场击杀"),
            ("opening_contact_rate", "首轮交火参与率"),
            ("far_teammate_ratio", "远离队友比例"),
            ("support_nearby_rate", "队友接敌时就近比例"),
        ]
        for column, (key, label) in zip(columns, card_keys):
            column.metric(
                label,
                _metric_value(metrics[key], match["map_name"]),
            )

        map_column, coach_column = st.columns([1.45, 0.8])
        with map_column:
            st.markdown(
                '<div class="cs2-panel-title">'
                "本场位置分布"
                "<small>热区 + 回合路线</small></div>",
                unsafe_allow_html=True,
            )
            overview_radar = build_radar_figure(
                database_path,
                analysis_id=match["analysis_id"],
                steamid=selected.steamid,
                map_name=match["map_name"],
                round_num=None,
                height=460,
            )
            if overview_radar is not None:
                st.plotly_chart(
                    overview_radar,
                    width="stretch",
                    key="overview_radar",
                )
            else:
                st.info("当前地图缺少本地雷达资源。")
        with coach_column:
            _render_coach_summary(facts, metrics)

        top_places = localize_text(
            match["map_name"],
            metrics["top_places"]["value"],
        )
        first_exits = localize_text(
            match["map_name"],
            metrics["first_exit_places"]["value"],
        )
        st.markdown(
            f'<div class="cs2-pill">活动区域：'
            f"{html.escape(top_places or '证据不足')}</div> "
            f'<div class="cs2-pill">常用离开出生区：'
            f"{html.escape(first_exits or '证据不足')}</div>",
            unsafe_allow_html=True,
        )
        pattern_summary = facts.get("tactical_patterns", {}).get("summary", {})
        if pattern_summary.get("dominant_zone"):
            rate = pattern_summary.get("dominant_zone_rate")
            st.markdown(
                "**战术模式线索：** "
                f"早期区域规则主要识别到 "
                f"{localize_text(match['map_name'], pattern_summary['dominant_zone'])} 区"
                + (
                    f"（{rate * 100:.0f}% 的有效路线回合）"
                    if isinstance(rate, (int, float))
                    else ""
                )
                + "。这只是基于位置和事件的行为识别。"
            )
        elif pattern_summary.get("zone_coverage", 0) < 0.5:
            st.caption(
                "当前地图尚未配置稳定的 A/B/中路区域映射，"
                "系统只展示真实地点名称，不强行给出大区域偏好。"
            )
        st.markdown("#### 回合时间线")
        timeline_rows = []
        for round_fact in facts["rounds"]:
            opening = (
                "首杀"
                if round_fact["opening_kill"]
                else "首死"
                if round_fact["opening_death"]
                else "首轮交火"
                if round_fact["opening_contact"]
                else "未参与首轮交火"
            )
            route = [
                localize_place_name(match["map_name"], place)
                for place in round_fact.get("early_route", [])
            ]
            timeline_rows.append(
                {
                    "回合": f"R{round_fact['round_num']}",
                    "结果": "获胜" if round_fact["team_won"] else "失利",
                    "K / D / A": (
                        f"{round_fact['kills']} / "
                        f"{round_fact['deaths']} / "
                        f"{round_fact['assists']}"
                    ),
                    "首轮交火": opening,
                    "早期路线": " → ".join(route) or "样本不足",
                }
            )
        st.dataframe(
            pd.DataFrame(timeline_rows),
            hide_index=True,
            width="stretch",
        )

        with st.expander("查看队伍经济变化", expanded=False):
            st.plotly_chart(
                build_economy_figure(
                    database_path,
                    analysis_id=match["analysis_id"],
                ),
                width="stretch",
                key="overview_economy",
            )

    with tabs[1]:
        _render_section_intro(
            "MAP VIEW",
            "位置与行动路线",
            "切换全场或单个回合，查看逐秒位置、热区与原始地点证据。",
        )
        round_options = ["全场"] + [
            f"第 {item['round_num']} 回合" for item in facts["rounds"]
        ]
        selected_round_label = st.selectbox(
            "地图范围",
            round_options,
            key="radar_round",
        )
        selected_round = (
            None
            if selected_round_label == "全场"
            else int(selected_round_label.removeprefix("第 ").removesuffix(" 回合"))
        )
        radar = build_radar_figure(
            database_path,
            analysis_id=match["analysis_id"],
            steamid=selected.steamid,
            map_name=match["map_name"],
            round_num=selected_round,
        )
        if radar is not None:
            st.plotly_chart(
                radar,
                width="stretch",
                key=f"position_radar_{selected_round or 'all'}",
            )
        else:
            st.info("当前地图缺少本地雷达资源，暂时无法绘制位置图。")

    with tabs[2]:
        keys = [
            ("excellent", "优秀回合"),
            ("problem", "优先复盘回合"),
            ("high_impact", "高影响回合"),
        ]
        grouped_rounds: dict[int, tuple[dict, list[str]]] = {}
        for category, title in keys:
            round_fact = facts["key_rounds"].get(category)
            if not round_fact:
                continue
            round_num = int(round_fact["round_num"])
            if round_num in grouped_rounds:
                grouped_rounds[round_num][1].append(title)
            else:
                grouped_rounds[round_num] = (round_fact, [title])

        for round_num, (round_fact, titles) in grouped_rounds.items():
            narrative = round_fact.get("narrative", {})
            st.markdown(
                f"""
                <div class="cs2-round-card">
                  <div class="cs2-kicker">{html.escape(" · ".join(titles))}</div>
                  <h3>第 {round_num} 回合 ·
                    {'本队获胜' if round_fact['team_won'] else '本队失利'}
                  </h3>
                  <div class="cs2-tag-row">
                    <span class="cs2-pill">K/D/A
                      {round_fact['kills']}/{round_fact['deaths']}/
                      {round_fact['assists']}
                    </span>
                    <span class="cs2-pill">路线
                      {html.escape(
                          " → ".join(
                              localize_place_name(
                                  match["map_name"],
                                  place,
                              )
                              for place in round_fact.get("early_route", [])
                          )
                          or "采样不足"
                      )}
                    </span>
                  </div>
                  <p>{html.escape(localize_text(
                      match["map_name"],
                      narrative.get("summary", "该回合证据不足"),
                  ))}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            with st.expander("可选方案与证据", expanded=False):
                for item in narrative.get("impact", []):
                    st.markdown(
                        f"- **影响：** "
                        f"{localize_text(match['map_name'], item)}"
                    )
                for item in narrative.get("alternatives", []):
                    st.markdown(
                        f"- **可尝试：** "
                        f"{localize_text(match['map_name'], item)}"
                    )
                evidence_ids = round_fact.get("decision_evidence_ids", [])
                if evidence_ids:
                    st.code("\n".join(evidence_ids), language=None)
            st.caption(
                "评分用于排序复盘优先级，不代表系统已确认真实意图。"
            )

    with tabs[3]:
        _render_section_intro(
            "ROUND REVIEW",
            "单回合决策复盘",
            "把地图位置、关键事件和队友阵亡后的可选行动放在同一条决策链里。",
        )
        round_num = st.selectbox(
            "选择要深入复盘的回合",
            [item["round_num"] for item in facts["rounds"]],
            key="detail_round",
        )
        round_fact = next(
            item for item in facts["rounds"] if item["round_num"] == round_num
        )
        detail_radar = build_radar_figure(
            database_path,
            analysis_id=match["analysis_id"],
            steamid=selected.steamid,
            map_name=match["map_name"],
            round_num=round_num,
        )
        if detail_radar is not None:
            st.plotly_chart(
                detail_radar,
                width="stretch",
                key=f"detail_radar_{round_num}",
            )
        timeline = _load_event_rows(
            database_path,
            match["analysis_id"],
            round_num,
        )
        if timeline.empty:
            st.info("该回合没有可展示的关键事件。")
        else:
            st.dataframe(timeline, hide_index=True, width="stretch")
        narrative = round_fact.get("narrative", {})
        st.markdown("#### 回合经过")
        st.markdown(
            localize_text(
                match["map_name"],
                narrative.get("summary", "证据不足"),
            )
        )
        if narrative.get("impact"):
            st.markdown("#### 这一回合产生了什么影响")
            for item in narrative["impact"]:
                st.markdown(
                    f"- {localize_text(match['map_name'], item)}"
                )
        death_contexts = round_fact.get("teammate_death_contexts", [])
        if death_contexts:
            st.markdown("#### 队友阵亡后，下一步应该做什么")
            for context in death_contexts:
                distance = context.get("distance_to_nearest_alive_teammate")
                distance_text = (
                    f"约 {distance:.0f} 世界坐标单位"
                    if isinstance(distance, (int, float))
                    else "未知"
                )
                teammate_death_place = localize_place_name(
                    match["map_name"],
                    context.get("teammate_death_place"),
                )
                player_place = localize_place_name(
                    match["map_name"],
                    context.get("player_place"),
                )
                nearest_place = localize_place_name(
                    match["map_name"],
                    context.get("nearest_alive_teammate_place"),
                )
                st.markdown(
                    f"- 第 {context['seconds_since_freeze']:.0f} 秒："
                    f"队友在 {teammate_death_place or '未知区域'}"
                    f"阵亡；你在 {player_place or '未知区域'}。"
                    f"最近存活队友在 "
                    f"{nearest_place or '未知区域'}"
                    f"（距离 {distance_text}）；"
                    f"当前存活 {context.get('teammates_alive')} 对 "
                    f"{context.get('enemies_alive')}。"
                )
                for suggestion in context.get("suggestions", []):
                    st.markdown(
                        "  - 建议："
                        + localize_text(match["map_name"], suggestion)
                    )
        round_patterns = next(
            (
                item["patterns"]
                for item in facts.get("tactical_patterns", {}).get(
                    "round_patterns", []
                )
                if item["round_num"] == round_num
            ),
            [],
        )
        if round_patterns:
            st.markdown("**可解释战术模式：**")
            for pattern in round_patterns:
                st.markdown(
                    f"- {localize_text(match['map_name'], pattern['label'])}："
                    f"{localize_text(match['map_name'], pattern['rationale'])}"
                    f"（置信度规则值 {pattern['confidence']:.2f}）"
                )
        if narrative.get("alternatives"):
            st.markdown("#### 下次遇到类似局面可以尝试")
            for item in narrative["alternatives"]:
                st.markdown(
                    f"- {localize_text(match['map_name'], item)}"
                )
            st.caption("以上是复盘建议，不是当时唯一正确答案。")

    with tabs[4]:
        _render_section_intro(
            "AI REPORT",
            "证据约束的教练复盘",
            "事实、行为推断和训练建议分层展示；原始证据编号按需展开。",
        )
        if st.session_state.get("report_warning"):
            st.warning(st.session_state["report_warning"])
        _render_structured_report(report, facts)
        with st.expander("查看完整 Markdown 报告原文", expanded=False):
            st.markdown(report.markdown)
        file_stem = f"{_safe_file_stem(player['name'])}_cs2_review"
        download_columns = st.columns(3)
        with download_columns[0]:
            st.download_button(
                "下载 Markdown",
                data=report.markdown.encode("utf-8"),
                file_name=f"{file_stem}.md",
                mime="text/markdown",
            )
        with download_columns[1]:
            st.download_button(
                "下载 Word",
                data=build_docx(
                    report.markdown,
                    fact_bundle=facts,
                    report=report,
                ),
                file_name=f"{file_stem}.docx",
                mime=(
                    "application/vnd.openxmlformats-officedocument."
                    "wordprocessingml.document"
                ),
            )
        with download_columns[2]:
            st.download_button(
                "下载 PDF",
                data=build_pdf(
                    report.markdown,
                    fact_bundle=facts,
                    report=report,
                ),
                file_name=f"{file_stem}.pdf",
                mime="application/pdf",
            )


def main() -> None:
    st.set_page_config(
        page_title="CS2 战术识别与智能复盘",
        page_icon="🎯",
        layout="wide",
    )
    _load_streamlit_secrets()
    _inject_global_styles()
    _render_brandbar()

    if access_control_required() and not st.session_state.get(
        "authenticated"
    ):
        required_code = access_code()
        if not required_code:
            st.error("服务器尚未配置访问口令，请联系项目维护者。")
            st.stop()
        _render_section_intro(
            "PRIVATE ACCESS",
            "进入战术复盘工作台",
            "输入项目维护者提供的访问口令。系统只分析行为倾向，不读取玩家真实想法。",
        )
        with st.form("access_form"):
            entered = st.text_input(
                "访问口令",
                type="password",
                autocomplete="current-password",
            )
            submitted = st.form_submit_button(
                "进入复盘工作台",
                type="primary",
            )
        if submitted:
            if hmac.compare_digest(entered, required_code):
                st.session_state["authenticated"] = True
                st.rerun()
            st.error("访问口令不正确。")
        st.stop()

    database_path = _render_upload()
    if database_path is None and st.session_state.get("database_path"):
        database_path = Path(st.session_state["database_path"])
    if database_path is not None:
        try:
            _render_analysis(database_path)
        except Exception as exc:
            st.error(f"分析失败：{exc}")
            with st.expander("排查信息"):
                st.exception(exc)
    else:
        st.markdown(
            """
            <div class="cs2-coach-card">
              <div class="cs2-coach-kicker">GET STARTED</div>
              <h3>上传一场 Demo，开始看懂自己的决策</h3>
              <p>系统会先解析真实事件和位置，再围绕你选择的玩家生成画像、关键回合、证据和训练建议。</p>
            </div>
            """,
            unsafe_allow_html=True,
        )


if __name__ == "__main__":
    main()

