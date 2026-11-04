"""Optional OpenAI-compatible report provider with evidence validation."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

from cs2_review.reporting import ReportDraft

REQUIRED_SECTIONS = {
    "profile": "本场玩家画像",
    "timeline": "回合时间线",
    "key_decisions": "关键决策分析",
    "round_review": "单回合复盘",
    "summary": "全场总结与训练建议",
    "evidence": "证据展示",
}
CLAIM_TYPES = {"observation", "inference", "recommendation"}
STEAM_ID_PATTERN = re.compile(r"\b\d{17}\b")
ROUND_PATTERN = re.compile(r"第\s*(\d+)\s*回合")
FORBIDDEN_PATTERNS = [
    re.compile(r"(百分百|100%)\s*(还原|确定|读取).{0,8}(心理|想法)"),
    re.compile(r"(系统|模型)\s*(已经)?(读取|确定)了?.{0,6}真实想法"),
]


class LLMReportError(RuntimeError):
    pass


class LLMValidationError(LLMReportError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


class JSONCompletionClient(Protocol):
    def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    errors: list[str]
    warnings: list[str]


def _strip_code_fence(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


class OpenAICompatibleHTTPClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 60.0,
        json_mode: bool = True,
        max_tokens: int = 8000,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.json_mode = json_mode
        self.max_tokens = max_tokens

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> dict[str, Any]:
        request_body: dict[str, Any] = {
            "model": self.model,
            "temperature": 0.2,
            "max_tokens": self.max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if self.json_mode:
            request_body["response_format"] = {"type": "json_object"}
        endpoint = (
            self.base_url
            if self.base_url.endswith("/chat/completions")
            else f"{self.base_url}/chat/completions"
        )
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(request_body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "cs2-review-undergraduate-project",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.timeout_seconds
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            message = exc.read(1000).decode("utf-8", errors="replace")
            raise LLMReportError(
                f"大模型接口返回 HTTP {exc.code}: {message}"
            ) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise LLMReportError(f"无法连接大模型接口: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise LLMReportError("大模型接口返回内容不是合法 JSON") from exc

        try:
            content = payload["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError("message.content is not text")
            decoded = json.loads(_strip_code_fence(content))
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise LLMReportError("无法从大模型响应中读取 JSON 报告") from exc
        if not isinstance(decoded, dict):
            raise LLMReportError("大模型报告顶层必须是 JSON 对象")
        return decoded


def _sanitize_text(text: str) -> str:
    return STEAM_ID_PATTERN.sub("[玩家]", text)


def _filter_evidence_references(
    value: Any,
    allowed_ids: set[str],
) -> Any:
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key in {
                "evidence_ids",
                "decision_evidence_ids",
                "allowed_evidence_ids",
            }:
                result[key] = [
                    evidence_id
                    for evidence_id in item
                    if evidence_id in allowed_ids
                ]
            else:
                result[key] = _filter_evidence_references(item, allowed_ids)
        return result
    if isinstance(value, list):
        return [
            _filter_evidence_references(item, allowed_ids)
            for item in value
        ]
    return value


def build_llm_fact_bundle(
    fact_bundle: dict[str, Any],
    *,
    max_evidence: int = 96,
) -> dict[str, Any]:
    """Build a minimized, de-identified fact bundle for an external model."""
    selected_ids: list[str] = []

    def add_ids(values: list[str], limit: int) -> None:
        for value in values[:limit]:
            if value not in selected_ids:
                selected_ids.append(value)

    for round_fact in fact_bundle["rounds"]:
        round_evidence_id = round_fact.get("round_evidence_id")
        if round_evidence_id:
            add_ids([round_evidence_id], 1)
    for category in ["excellent", "problem", "high_impact"]:
        key_round = fact_bundle["key_rounds"].get(category)
        if key_round:
            add_ids(key_round.get("decision_evidence_ids", []), 8)
            for context in key_round.get("teammate_death_contexts", []):
                add_ids(context.get("evidence_ids", []), 2)
    for metric in fact_bundle["metrics"]:
        add_ids(metric.get("evidence_ids", []), 2)

    evidence_by_id = {
        item["evidence_id"]: item for item in fact_bundle.get("evidence", [])
    }
    allowed_ids = [
        evidence_id for evidence_id in selected_ids
        if evidence_id in evidence_by_id
    ][:max_evidence]

    sanitized_metrics = []
    for metric in fact_bundle["metrics"]:
        evidence_ids = [
            evidence_id for evidence_id in metric.get("evidence_ids", [])
            if evidence_id in allowed_ids
        ]
        sanitized_metrics.append(
            {
                "key": metric["key"],
                "label": metric["label"],
                "value": metric["value"],
                "unit": metric["unit"],
                "sample_size": metric["sample_size"],
                "confidence": metric["confidence"],
                "definition": metric["definition"],
                "evidence_ids": evidence_ids,
            }
        )

    key_round_numbers = {
        int(item["round_num"])
        for item in fact_bundle["key_rounds"].values()
        if isinstance(item, dict) and "round_num" in item
    }
    sanitized_rounds = []
    for item in fact_bundle["rounds"]:
        compact = {
            "round_num": item["round_num"],
            "round_evidence_id": item.get("round_evidence_id"),
            "selected_side": item.get("selected_side"),
            "team_won": item.get("team_won"),
            "game_state": item.get("game_state"),
            "score_before": item.get("score_before"),
            "economy": item.get("economy"),
            "kills": item.get("kills"),
            "deaths": item.get("deaths"),
            "assists": item.get("assists"),
            "opening_contact": item.get("opening_contact"),
            "opening_kill": item.get("opening_kill"),
            "opening_death": item.get("opening_death"),
            "survived": item.get("survived"),
            "first_exit_place": item.get("first_exit_place"),
            "early_route": item.get("early_route"),
            "nearest_teammate_distance_median": item.get(
                "nearest_teammate_distance_median"
            ),
            "support_distance": item.get("support_distance"),
            "support_responded_within_5s": item.get(
                "support_responded_within_5s"
            ),
            "utility_events": item.get("utility_events"),
            "excellent_score": item.get("excellent_score"),
            "problem_score": item.get("problem_score"),
            "impact_score": item.get("impact_score"),
            "teammate_death_count": len(
                item.get("teammate_death_contexts", [])
            ),
            "decision_evidence_ids": [
                evidence_id
                for evidence_id in item.get("decision_evidence_ids", [])[:4]
                if evidence_id in allowed_ids
            ],
        }
        if int(item["round_num"]) in key_round_numbers:
            compact["narrative"] = _filter_evidence_references(
                item.get("narrative", {}), set(allowed_ids)
            )
            compact["teammate_death_contexts"] = (
                _filter_evidence_references(
                    item.get("teammate_death_contexts", [])[:5],
                    set(allowed_ids),
                )
            )
        sanitized_rounds.append(compact)

    sanitized_key_rounds = {}
    for category, item in fact_bundle["key_rounds"].items():
        if item is None or not isinstance(item, dict):
            sanitized_key_rounds[category] = item
            continue
        sanitized_key_rounds[category] = _filter_evidence_references(
            {
                key: item.get(key)
                for key in [
                    "round_num",
                    "selected_side",
                    "team_won",
                    "game_state",
                    "economy",
                    "kills",
                    "deaths",
                    "assists",
                    "opening_contact",
                    "opening_kill",
                    "opening_death",
                    "survived",
                    "early_route",
                    "nearest_teammate_distance_median",
                    "support_distance",
                    "support_responded_within_5s",
                    "utility_events",
                    "positive_components",
                    "problem_components",
                    "excellent_score",
                    "problem_score",
                    "impact_score",
                    "narrative",
                    "teammate_death_contexts",
                    "decision_evidence_ids",
                ]
            },
            set(allowed_ids),
        )

    tactical = fact_bundle.get("tactical_patterns", {})
    sanitized_patterns = {
        "rule_version": tactical.get("rule_version"),
        "summary": _filter_evidence_references(
            tactical.get("summary", {}), set(allowed_ids)
        ),
        "key_round_patterns": _filter_evidence_references(
            [
                item for item in tactical.get("round_patterns", [])
                if int(item["round_num"]) in key_round_numbers
            ],
            set(allowed_ids),
        ),
        "limitations": tactical.get("limitations", []),
    }

    sanitized_evidence = []
    for evidence_id in allowed_ids:
        item = evidence_by_id[evidence_id]
        sanitized_evidence.append(
            {
                "evidence_id": evidence_id,
                "type": item.get("type"),
                "round_num": item.get("round_num"),
                "tick": item.get("tick"),
                "summary": _sanitize_text(str(item.get("summary", ""))),
            }
        )

    return {
        "schema_version": "llm-fact-v1",
        "match": {
            "map_name": fact_bundle["match"]["map_name"],
            "round_count": fact_bundle["match"]["round_count"],
            "score": fact_bundle["match"]["score"],
        },
        "player": {
            "display_name": "目标玩家",
            "starting_side": fact_bundle["player"]["starting_side"],
        },
        "metrics": sanitized_metrics,
        "rounds": sanitized_rounds,
        "key_rounds": sanitized_key_rounds,
        "tactical_patterns": sanitized_patterns,
        "evidence": sanitized_evidence,
        "allowed_evidence_ids": allowed_ids,
        "analysis_limits": fact_bundle.get("analysis_limits", []),
    }


def _ensure_complete_timeline(
    payload: dict[str, Any],
    llm_fact_bundle: dict[str, Any],
) -> dict[str, Any]:
    """Fill omitted round summaries from deterministic facts.

    Long matches can exhaust the model's output budget. The model still writes
    the analysis sections, while the factual one-line timeline stays complete.
    """
    sections = payload.get("sections")
    if not isinstance(sections, list):
        return payload
    timeline = next(
        (
            section for section in sections
            if isinstance(section, dict) and section.get("key") == "timeline"
        ),
        None,
    )
    if timeline is None:
        return payload
    claims = timeline.get("claims")
    if not isinstance(claims, list):
        return payload
    mentioned = {
        int(match.group(1))
        for claim in claims
        if isinstance(claim, dict)
        for match in ROUND_PATTERN.finditer(str(claim.get("text", "")))
    }
    for item in llm_fact_bundle["rounds"]:
        round_num = int(item["round_num"])
        if round_num in mentioned:
            continue
        result = (
            "本队获胜"
            if item.get("team_won") is True
            else "本队失利"
            if item.get("team_won") is False
            else "结果未知"
        )
        opening = (
            "首杀"
            if item.get("opening_kill")
            else "首死"
            if item.get("opening_death")
            else "参与首轮交火"
            if item.get("opening_contact")
            else "未参与首轮交火"
        )
        route = " → ".join(item.get("early_route") or []) or "采样不足"
        claims.append(
            {
                "text": (
                    f"第 {round_num} 回合：{result}，"
                    f"K/D/A={item.get('kills', 0)}/"
                    f"{item.get('deaths', 0)}/"
                    f"{item.get('assists', 0)}，{opening}，"
                    f"早期路线={route}。"
                ),
                "claim_type": "observation",
                "evidence_ids": [
                    evidence_id
                    for evidence_id in [
                        item.get("round_evidence_id"),
                        *(item.get("decision_evidence_ids") or [])[:2],
                    ]
                    if evidence_id
                ],
            }
        )
    return payload


def validate_llm_payload(
    payload: dict[str, Any],
    llm_fact_bundle: dict[str, Any],
) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    allowed_evidence = set(llm_fact_bundle["allowed_evidence_ids"])
    allowed_rounds = {
        int(item["round_num"]) for item in llm_fact_bundle["rounds"]
    }

    if not isinstance(payload.get("title"), str) or not payload["title"].strip():
        errors.append("报告缺少非空 title")
    sections = payload.get("sections")
    if not isinstance(sections, list):
        errors.append("报告 sections 必须是数组")
        return ValidationResult(False, errors, warnings)

    by_key: dict[str, dict[str, Any]] = {}
    for section in sections:
        if not isinstance(section, dict):
            errors.append("sections 中存在非对象元素")
            continue
        key = section.get("key")
        if key not in REQUIRED_SECTIONS:
            warnings.append(f"忽略未知章节 key={key}")
            continue
        if key in by_key:
            errors.append(f"章节重复: {key}")
        by_key[str(key)] = section

    missing = set(REQUIRED_SECTIONS) - set(by_key)
    if missing:
        errors.append(f"缺少章节: {sorted(missing)}")

    referenced_ids: set[str] = set()
    for key, section in by_key.items():
        claims = section.get("claims")
        if not isinstance(claims, list) or not claims:
            errors.append(f"章节 {key} 缺少 claims")
            continue
        for index, claim in enumerate(claims):
            label = f"{key}.claims[{index}]"
            if not isinstance(claim, dict):
                errors.append(f"{label} 不是对象")
                continue
            text = claim.get("text")
            claim_type = claim.get("claim_type")
            evidence_ids = claim.get("evidence_ids", [])
            if not isinstance(text, str) or not text.strip():
                errors.append(f"{label} 缺少 text")
                text = ""
            if claim_type not in CLAIM_TYPES:
                errors.append(f"{label} claim_type 非法: {claim_type}")
            if not isinstance(evidence_ids, list):
                errors.append(f"{label} evidence_ids 必须是数组")
                evidence_ids = []
            unknown = {
                str(value) for value in evidence_ids
                if str(value) not in allowed_evidence
            }
            if unknown:
                errors.append(f"{label} 引用未知证据: {sorted(unknown)}")
            referenced_ids.update(str(value) for value in evidence_ids)
            if claim_type in {"observation", "inference"} and not evidence_ids:
                errors.append(f"{label} 事实或推断未引用证据")
            for round_match in ROUND_PATTERN.finditer(text):
                round_num = int(round_match.group(1))
                if round_num not in allowed_rounds:
                    errors.append(f"{label} 引用不存在的第 {round_num} 回合")
            if any(pattern.search(text) for pattern in FORBIDDEN_PATTERNS):
                errors.append(f"{label} 含读心或绝对化表述")

    timeline = by_key.get("timeline")
    if timeline:
        timeline_text = " ".join(
            str(claim.get("text", ""))
            for claim in timeline.get("claims", [])
            if isinstance(claim, dict)
        )
        mentioned_rounds = {
            int(match.group(1))
            for match in ROUND_PATTERN.finditer(timeline_text)
        }
        missing_rounds = sorted(allowed_rounds - mentioned_rounds)
        if missing_rounds:
            errors.append(
                f"回合时间线未逐回合覆盖: {missing_rounds}"
            )

    if not referenced_ids:
        errors.append("整份报告没有引用任何证据")
    if not any("行为推断" in str(section) for section in sections):
        warnings.append("报告未明确出现“行为推断”提示")

    return ValidationResult(not errors, errors, warnings)


def render_llm_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# {payload['title']}",
        "",
        "> 本报告的大模型输出受结构化事实包和证据编号约束。"
        "“倾向”属于行为推断，不等于读取玩家真实想法。",
        "",
    ]
    section_map = {item["key"]: item for item in payload["sections"]}
    for index, (key, default_title) in enumerate(
        REQUIRED_SECTIONS.items(), start=1
    ):
        section = section_map[key]
        lines.extend([f"## {index}. {section.get('title') or default_title}", ""])
        for claim in section["claims"]:
            tags = {
                "observation": "事实",
                "inference": "行为推断",
                "recommendation": "建议",
            }
            evidence_ids = claim.get("evidence_ids", [])
            suffix = (
                f"（证据：{'、'.join(evidence_ids)}）"
                if evidence_ids
                else ""
            )
            lines.append(
                f"- **[{tags[claim['claim_type']]}]** "
                f"{claim['text']}{suffix}"
            )
        lines.append("")
    return "\n".join(lines).strip() + "\n"


class OpenAICompatibleReportProvider:
    name = "openai-compatible"
    prompt_version = "grounded-review-v0.1"

    def __init__(
        self,
        client: JSONCompletionClient,
        *,
        model: str,
    ) -> None:
        self.client = client
        self.model = model

    @classmethod
    def from_deepseek(
        cls,
    ) -> "OpenAICompatibleReportProvider":
        api_key = (
            os.getenv("DEEPSEEK_API_KEY", "").strip()
            or os.getenv("LLM_API_KEY", "").strip()
        )
        base_url = os.getenv(
            "DEEPSEEK_BASE_URL",
            "https://api.deepseek.com/v1",
        ).strip()
        model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip()
        timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
        max_tokens = int(os.getenv("LLM_MAX_TOKENS", "8000"))
        if not api_key:
            raise LLMReportError(
                "未配置 DEEPSEEK_API_KEY，DeepSeek 报告不可用"
            )
        client = OpenAICompatibleHTTPClient(
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout_seconds=timeout,
            json_mode=True,
            max_tokens=max_tokens,
        )
        return cls(client, model=model)


    def generate(self, fact_bundle: dict[str, Any]) -> ReportDraft:
        llm_facts = build_llm_fact_bundle(fact_bundle)
        system_prompt = (
            "你是《CS2》赛后复盘助手。只能使用用户提供的事实包，"
            "不得补充未出现的比分、回合、事件或心理活动。"
            "事实类和行为推断类 claim 必须引用 allowed_evidence_ids 中的证据。"
            "建议类内容必须标记为 recommendation。"
            "如果事实包包含 teammate_death_contexts，请优先解释队友阵亡时"
            "玩家所在位置、死亡地点、两者距离、最近存活队友位置、双方人数、"
            "带包和已下包状态。建议要明确指出可向哪个已记录地点靠拢、"
            "应重组还是保持交叉火力，不能编造地形或要求不存在的队友配合。"
            "整体语气采用温和、具体、行动导向的教练式反馈，指出可尝试的改进，"
            "避免羞辱、绝对化或把赛后信息当成玩家当时已知的信息。"
            "输出严格 JSON，不要输出 Markdown 代码块。"
        )
        schema = {
            "title": "string",
            "sections": [
                {
                    "key": "profile|timeline|key_decisions|round_review|summary|evidence",
                    "title": "string",
                    "claims": [
                        {
                            "text": "string",
                            "claim_type": "observation|inference|recommendation",
                            "evidence_ids": ["string"],
                        }
                    ],
                }
            ],
        }
        user_prompt = (
            "请生成六个章节：本场玩家画像、回合时间线、关键决策分析、"
            "单回合复盘、全场总结与训练建议、证据展示。"
            "时间线必须为事实包中的每一个回合单独写一条 claim，"
            "不得把多个回合合并成一条。"
            "描述范围只能使用“本场”，不得写成“本赛季”或扩展到历史比赛。"
            "每条事实或行为推断都要附证据 ID；没有证据时明确写证据不足。"
            "措辞使用“系统判断”或“行为倾向”，不得声称读取心理。"
            f"JSON 结构示例：{json.dumps(schema, ensure_ascii=False)}。"
            "事实包如下：\n"
            + json.dumps(llm_facts, ensure_ascii=False, indent=2)
        )
        payload = self.client.complete_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        payload = _ensure_complete_timeline(payload, llm_facts)
        validation = validate_llm_payload(payload, llm_facts)
        repair_attempted = False
        if not validation.valid:
            repair_attempted = True
            repair_prompt = (
                "下面是一份未通过证据校验的报告 JSON。请修复它并只输出合法 JSON。"
                "不得增加新事实；每个 claim 都必须带有 allowed_evidence_ids "
                "中的非空证据；没有证据的 claim 请删除。不得改写已有证据编号。"
                f"校验错误：{json.dumps(validation.errors, ensure_ascii=False)}\n"
                f"允许的证据编号："
                f"{json.dumps(llm_facts['allowed_evidence_ids'], ensure_ascii=False)}\n"
                f"原报告：{json.dumps(payload, ensure_ascii=False)}"
            )
            repaired_payload = self.client.complete_json(
                system_prompt=system_prompt,
                user_prompt=repair_prompt,
            )
            repair_validation = validate_llm_payload(
                repaired_payload, llm_facts
            )
            if not repair_validation.valid:
                raise LLMValidationError(repair_validation.errors)
            payload = repaired_payload
            validation = repair_validation
        return ReportDraft(
            provider=self.name,
            provider_model=self.model,
            markdown=render_llm_markdown(payload),
            structured={
                **payload,
                "validation": {
                    "valid": True,
                    "warnings": validation.warnings,
                    "repair_attempted": repair_attempted,
                },
                "prompt_version": self.prompt_version,
            },
        )

