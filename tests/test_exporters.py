from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path

from docx import Document

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cs2_review.exporters import build_docx, build_pdf
from cs2_review.reporting import ReportDraft


class ReportExporterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.markdown = """# 测试战术复盘

## 1. 本场玩家画像

**打法定性。** 温和而具体地描述玩家行为。

- 行动路线：Outside
- 训练目标：保持交叉火力

## 2. 回合时间线

1. **第 1 回合：** 队友阵亡后重新集合。
"""
        self.facts = {
            "player": {"name": "Test Player"},
            "match": {"map_name": "de_nuke"},
        }
        self.report = ReportDraft(
            provider="test",
            markdown=self.markdown,
            structured={},
        )

    def test_docx_contains_clean_chinese_report(self) -> None:
        content = build_docx(
            self.markdown,
            fact_bundle=self.facts,
            report=self.report,
        )
        self.assertTrue(content.startswith(b"PK"))
        document = Document(io.BytesIO(content))
        text = "\n".join(paragraph.text for paragraph in document.paragraphs)
        self.assertIn("测试战术复盘", text)
        self.assertIn("打法定性", text)
        self.assertNotIn("**", text)

    def test_pdf_is_generated(self) -> None:
        content = build_pdf(
            self.markdown,
            fact_bundle=self.facts,
            report=self.report,
        )
        self.assertTrue(content.startswith(b"%PDF"))
        self.assertGreater(len(content), 5000)


if __name__ == "__main__":
    unittest.main()

