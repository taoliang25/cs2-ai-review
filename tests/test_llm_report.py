from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cs2_review.llm_report import (
    REQUIRED_SECTIONS,
    OpenAICompatibleHTTPClient,
    OpenAICompatibleReportProvider,
    build_llm_fact_bundle,
    validate_llm_payload,
)


def _bundle() -> dict:
    evidence_id = "E-DEMO-R01-0000100-KILL-0001"
    rounds = [
        {
            "round_num": 1,
            "start_tick": 1,
            "freeze_end_tick": 64,
            "end_tick": 5000,
            "selected_side": "terrorist",
            "team_won": True,
            "kills": 1,
            "deaths": 0,
            "assists": 0,
            "opening_kill": True,
            "opening_death": False,
            "decision_evidence_ids": [evidence_id],
            "evidence_ids": [evidence_id],
        }
    ]
    return {
        "schema_version": "1.0",
        "rule_version": "test",
        "match": {
            "analysis_id": "a" * 64,
            "map_name": "de_mirage",
            "round_count": 1,
            "score": {"terrorist": 1, "counter-terrorist": 0},
        },
        "player": {
            "steamid": "76561190000000000",
            "name": "测试玩家",
            "starting_side": "terrorist",
        },
        "metrics": [
            {
                "key": "opening_kills",
                "label": "每回合首杀次数",
                "value": 1,
                "unit": "次",
                "sample_size": 1,
                "confidence": 0.1,
                "definition": "测试定义",
                "evidence_ids": [evidence_id],
            }
        ],
        "rounds": rounds,
        "key_rounds": {
            "excellent": rounds[0],
            "problem": None,
            "high_impact": rounds[0],
            "clutches": [],
        },
        "evidence": [
            {
                "evidence_id": evidence_id,
                "type": "kill",
                "round_num": 1,
                "tick": 100,
                "x": 123.0,
                "y": 456.0,
                "summary": "玩家 76561190000000000 取得击杀",
            }
        ],
        "analysis_limits": ["单场数据不能证明长期习惯"],
    }


def _payload() -> dict:
    evidence_id = "E-DEMO-R01-0000100-KILL-0001"
    return {
        "title": "de_mirage 个人复盘",
        "sections": [
            {
                "key": key,
                "title": title,
                "claims": [
                    {
                        "text": (
                            "第 1 回合中，系统判断玩家参与了首轮交火。"
                            if key == "timeline"
                            else "该结论来自测试事实。"
                        ),
                        "claim_type": "observation",
                        "evidence_ids": [evidence_id],
                    }
                ],
            }
            for key, title in REQUIRED_SECTIONS.items()
        ],
    }


class FakeClient:
    def __init__(self, payload: dict, user_prompt: str = "") -> None:
        self.payload = payload
        self.user_prompt = user_prompt

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> dict:
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        return copy.deepcopy(self.payload)


class StubHTTPClient(OpenAICompatibleHTTPClient):
    def __init__(self, payloads: list[dict]) -> None:
        super().__init__(
            base_url="https://example.invalid/v1",
            api_key="test-key",
            model="test-model",
            json_mode=True,
        )
        self.payloads = payloads
        self.request_bodies: list[dict] = []

    def _post_completion(self, request_body: dict) -> dict:
        self.request_bodies.append(copy.deepcopy(request_body))
        return self.payloads.pop(0)


class LLMReportTest(unittest.TestCase):
    def test_sanitized_bundle_removes_identity_and_coordinates(self) -> None:
        bundle = _bundle()
        llm_bundle = build_llm_fact_bundle(bundle)
        serialized = json.dumps(llm_bundle, ensure_ascii=False)
        self.assertNotIn("76561190000000000", serialized)
        self.assertNotIn("测试玩家", serialized)
        self.assertNotIn('"x"', serialized)
        self.assertEqual(llm_bundle["player"]["display_name"], "目标玩家")

    def test_llm_bundle_uses_local_map_callouts(self) -> None:
        bundle = _bundle()
        bundle["match"]["map_name"] = "de_dust2"
        bundle["rounds"][0]["first_exit_place"] = "OutsideTunnel"
        bundle["rounds"][0]["early_route"] = [
            "OutsideTunnel",
            "UpperTunnel",
            "BombsiteA",
        ]
        llm_bundle = build_llm_fact_bundle(bundle)
        route = llm_bundle["rounds"][0]["early_route"]
        self.assertEqual(route, ["B洞外", "B洞", "A包"])

    def test_valid_structured_report(self) -> None:
        llm_bundle = build_llm_fact_bundle(_bundle())
        result = validate_llm_payload(_payload(), llm_bundle)
        self.assertTrue(result.valid, result.errors)

    def test_unknown_evidence_is_rejected(self) -> None:
        llm_bundle = build_llm_fact_bundle(_bundle())
        payload = _payload()
        payload["sections"][0]["claims"][0]["evidence_ids"] = ["E-NOT-REAL"]
        result = validate_llm_payload(payload, llm_bundle)
        self.assertFalse(result.valid)
        self.assertTrue(any("未知证据" in item for item in result.errors))

    def test_forbidden_mind_reading_is_rejected(self) -> None:
        llm_bundle = build_llm_fact_bundle(_bundle())
        payload = _payload()
        payload["sections"][0]["claims"][0]["text"] = (
            "系统百分百还原玩家真实想法。"
        )
        result = validate_llm_payload(payload, llm_bundle)
        self.assertFalse(result.valid)

    def test_provider_generates_grounded_report(self) -> None:
        client = FakeClient(_payload())
        provider = OpenAICompatibleReportProvider(client, model="fake-model")
        report = provider.generate(_bundle())
        self.assertEqual(report.provider_model, "fake-model")
        self.assertIn("证据", report.markdown)
        self.assertNotIn("76561190000000000", client.user_prompt)
        self.assertNotIn("测试玩家", client.user_prompt)

    def test_http_client_retries_without_json_mode(self) -> None:
        invalid_payload = {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": "not-json"},
                }
            ]
        }
        valid_payload = {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": '{"ok": true}'},
                }
            ]
        }
        client = StubHTTPClient([invalid_payload, valid_payload])
        result = client.complete_json(
            system_prompt="system",
            user_prompt="user",
        )
        self.assertEqual(result, {"ok": True})
        self.assertEqual(len(client.request_bodies), 2)
        self.assertIn("response_format", client.request_bodies[0])
        self.assertNotIn("response_format", client.request_bodies[1])

    def test_http_client_accepts_text_content_parts(self) -> None:
        client = StubHTTPClient([])
        payload = {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "content": [
                            {"type": "text", "text": '{"ok":'},
                            {"type": "text", "text": " true}"},
                        ]
                    },
                }
            ]
        }
        self.assertEqual(client._decode_completion(payload), {"ok": True})


if __name__ == "__main__":
    unittest.main()

