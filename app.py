"""Single-page Streamlit MVP for one-player CS2 demo review."""

from __future__ import annotations

import hashlib
import hmac
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
    st.subheader("1. 上传单场 Demo")
    uploaded = st.file_uploader(
        "选择 CS2 常规 5v5 Demo",
        type=["dem"],
        help="首版一次只分析一场 .dem。Demo 可能包含玩家标识，默认仅在本机处理。",
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
                temporary = work_dir / f".uploading-{uuid.uuid4().hex}.dem"
                digest = hashlib.sha256()
                with temporary.open("wb") as stream:
                    while chunk := uploaded.read(8 * 1024 * 1024):
                        digest.update(chunk)
                        stream.write(chunk)
                saved = work_dir / f"upload-{digest.hexdigest()[:12]}.dem"
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
        sorted(DEMO_DIR.glob("*.dem")) if DEMO_DIR.is_dir() else []
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
            SAMPLE_DEMO if SAMPLE_DEMO in cached_demos else cached_demos[0],
        )
        selected_demo = st.selectbox(
            "已缓存验证 Demo",
            cached_demos,
            index=cached_demos.index(preferred),
            format_func=lambda path: path.name,
        )
        st.caption("开发环境可复用已授权的测试 Demo，也可直接上传自己的 Demo。")
        if st.button("载入已缓存的测试 Demo"):
            return _parse_or_reuse(selected_demo, temporary=False)
    return None


def _metric_value(metric: dict) -> str:
    value = metric["value"]
    if value is None:
        return "证据不足"
    if metric["unit"] == "比例" and isinstance(value, (int, float)):
        return f"{value * 100:.0f}%"
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


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
        st.caption("本地分析会话")
        st.code(analysis["map_name"] or "未知地图")
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

    st.subheader("2. 选择主要分析玩家")
    labels = {
        f"{player.name}｜{player.starting_side or '未知阵营'}｜{player.steamid}":
        player
        for player in players
    }
    selected_label = st.selectbox("点击选择玩家", list(labels))
    selected: PlayerOption = labels[selected_label]

    if st.button("生成本场画像与复盘", type="primary"):
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
        st.info("分析玩家已更改，请点击“生成本场画像与复盘”。")
        return

    match = facts["match"]
    player = facts["player"]
    metrics = {item["key"]: item for item in facts["metrics"]}
    report = st.session_state["report"]

    header_left, header_right = st.columns([3, 1])
    with header_left:
        st.header(f"{player['name']} 的《{match['map_name']}》复盘")
    with header_right:
        st.metric(
            "比分 T / CT",
            f"{match['score']['terrorist']} / "
            f"{match['score']['counter-terrorist']}",
        )

    tabs = st.tabs(
        ["全场总览", "位置与路线", "关键回合", "单回合复盘", "智能复盘报告"]
    )
    with tabs[0]:
        columns = st.columns(4)
        card_keys = [
            ("kills", "击杀"),
            ("opening_contact_rate", "首轮交火参与率"),
            ("far_teammate_ratio", "远离队友比例"),
            ("support_nearby_rate", "队友接敌时就近比例"),
        ]
        for column, (key, label) in zip(columns, card_keys):
            column.metric(label, _metric_value(metrics[key]))

        st.markdown(
            f"**活动区域：** {metrics['top_places']['value'] or '证据不足'}  \n"
            f"**常用离开出生区地点：** "
            f"{metrics['first_exit_places']['value'] or '证据不足'}"
        )
        pattern_summary = facts.get("tactical_patterns", {}).get("summary", {})
        if pattern_summary.get("dominant_zone"):
            rate = pattern_summary.get("dominant_zone_rate")
            st.markdown(
                "**战术模式线索：** "
                f"早期区域规则主要识别到 "
                f"{pattern_summary['dominant_zone']} 区"
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
        for round_fact in facts["rounds"]:
            result = "胜" if round_fact["team_won"] else "负"
            opening = (
                "首杀"
                if round_fact["opening_kill"]
                else "首死"
                if round_fact["opening_death"]
                else "首轮交火"
                if round_fact["opening_contact"]
                else "未参与首轮交火"
            )
            st.markdown(
                f"**R{round_fact['round_num']} · {result}**  "
                f"K/D/A {round_fact['kills']}/{round_fact['deaths']}/"
                f"{round_fact['assists']} · {opening} · "
                f"{' → '.join(round_fact['early_route']) or '路线样本不足'}"
            )

        st.markdown("#### 回合经济")
        st.plotly_chart(
            build_economy_figure(
                database_path,
                analysis_id=match["analysis_id"],
            ),
            width="stretch",
        )

    with tabs[1]:
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
            st.plotly_chart(radar, width="stretch")
        else:
            st.info("当前地图缺少本地雷达资源，暂时无法绘制位置图。")

    with tabs[2]:
        keys = [
            ("excellent", "优秀回合"),
            ("problem", "优先复盘回合"),
            ("high_impact", "高影响回合"),
        ]
        for category, title in keys:
            round_fact = facts["key_rounds"].get(category)
            if not round_fact:
                continue
            narrative = round_fact.get("narrative", {})
            st.markdown(
                f"### {title}：第 {round_fact['round_num']} 回合\n\n"
                f"{narrative.get('summary', '')}\n\n"
                f"- 本队结果："
                f"{'获胜' if round_fact['team_won'] else '失利'}\n"
                f"- K/D/A：{round_fact['kills']}/"
                f"{round_fact['deaths']}/{round_fact['assists']}\n"
                f"- 早期路线："
                f"{' → '.join(round_fact['early_route']) or '采样不足'}\n"
                f"- 系统评分：优先复盘分 {round_fact['problem_score']:.2f}；"
                f"综合影响分 {round_fact['impact_score']:.2f}\n"
                "- 说明：评分用于排序复盘优先级，不代表系统已确认真实意图。"
            )

    with tabs[3]:
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
            st.plotly_chart(detail_radar, width="stretch")
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
        st.markdown(f"**回合经过：** {narrative.get('summary', '证据不足')}")
        if narrative.get("impact"):
            st.markdown("**可观测影响：**")
            for item in narrative["impact"]:
                st.markdown(f"- {item}")
        death_contexts = round_fact.get("teammate_death_contexts", [])
        if death_contexts:
            st.markdown("**队友阵亡后的位置上下文：**")
            for context in death_contexts:
                distance = context.get("distance_to_nearest_alive_teammate")
                distance_text = (
                    f"约 {distance:.0f} 世界坐标单位"
                    if isinstance(distance, (int, float))
                    else "未知"
                )
                st.markdown(
                    f"- 第 {context['seconds_since_freeze']:.0f} 秒："
                    f"队友在 {context.get('teammate_death_place') or '未知区域'}"
                    f"阵亡；你在 {context.get('player_place') or '未知区域'}。"
                    f"最近存活队友在 "
                    f"{context.get('nearest_alive_teammate_place') or '未知区域'}"
                    f"（距离 {distance_text}）；"
                    f"当前存活 {context.get('teammates_alive')} 对 "
                    f"{context.get('enemies_alive')}。"
                )
                for suggestion in context.get("suggestions", []):
                    st.markdown(f"  - 建议：{suggestion}")
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
                    f"- {pattern['label']}：{pattern['rationale']}"
                    f"（置信度规则值 {pattern['confidence']:.2f}）"
                )
        if narrative.get("alternatives"):
            st.markdown("**赛后可选方案：**")
            for item in narrative["alternatives"]:
                st.markdown(f"- {item}")
            st.caption("以上是复盘建议，不是当时唯一正确答案。")

    with tabs[4]:
        st.caption(
            f"报告提供方：{report.provider}"
            + (
                f" / {report.provider_model}"
                if report.provider_model
                else " / 本地模板"
            )
        )
        if st.session_state.get("report_warning"):
            st.warning(st.session_state["report_warning"])
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
    st.title("CS2 战术识别与赛后智能复盘")
    st.caption(
        "单场 Demo · 单个玩家 · 事件证据驱动。"
        "系统分析行为倾向，不读取玩家真实想法。"
    )

    if access_control_required() and not st.session_state.get(
        "authenticated"
    ):
        required_code = access_code()
        if not required_code:
            st.error("服务器尚未配置访问口令，请联系项目维护者。")
            st.stop()
        st.subheader("访问验证")
        with st.form("access_form"):
            entered = st.text_input(
                "访问口令",
                type="password",
                autocomplete="current-password",
            )
            submitted = st.form_submit_button("进入")
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
        st.info("请上传一场常规 5v5 CS2 Demo，或载入已缓存的测试样本。")


if __name__ == "__main__":
    main()

