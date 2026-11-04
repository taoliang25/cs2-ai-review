from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DEMO = (
    PROJECT_ROOT
    / "data"
    / "demo"
    / "research_demoparser_test_demo.dem"
)


@unittest.skipUnless(SAMPLE_DEMO.is_file(), "Local validation demo is not present")
class StreamlitAppTest(unittest.TestCase):
    def test_access_code_gate(self) -> None:
        with patch.dict(
            os.environ,
            {
                "APP_REQUIRE_ACCESS": "true",
                "APP_ACCESS_CODE": "test-access-code",
            },
        ):
            app = AppTest.from_file(
                str(PROJECT_ROOT / "app.py")
            ).run(timeout=30)
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(len(app.text_input), 1)
            self.assertEqual(len(app.selectbox), 0)
            app.text_input[0].input("test-access-code")
            app.button[0].click().run(timeout=30)
            self.assertEqual(len(app.exception), 0)
            self.assertGreaterEqual(len(app.selectbox), 1)

    def test_sample_demo_to_report_flow(self) -> None:
        with patch.dict(os.environ, {"APP_REQUIRE_ACCESS": "false"}):
            app = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run(timeout=30)
            self.assertEqual(len(app.exception), 0)

            load_button = next(
                button for button in app.button
                if "测试 Demo" in button.label
            )
            load_button.click().run(timeout=60)
            self.assertEqual(len(app.exception), 0)
            player_select = next(
                item for item in app.selectbox
                if item.label == "点击选择玩家"
            )
            self.assertEqual(len(player_select.options), 10)

            analyze_button = next(
                button for button in app.button
                if "生成 AI 画像" in button.label
            )
            analyze_button.click().run(timeout=60)
            self.assertEqual(len(app.exception), 0)
            self.assertGreaterEqual(len(app.tabs), 5)
            self.assertTrue(app.metric)
            labels = [
                item.label for item in app.get("download_button")
            ]
            self.assertIn("下载 Markdown", labels)
            self.assertIn("下载 Word", labels)
            self.assertIn("下载 PDF", labels)


if __name__ == "__main__":
    unittest.main()

