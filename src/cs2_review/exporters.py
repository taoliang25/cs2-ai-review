"""Word and PDF exporters for evidence-backed CS2 review reports."""

from __future__ import annotations

import html
import io
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

from cs2_review.reporting import ReportDraft

_INLINE_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_NUMBERED_ITEM = re.compile(r"^(\d+)\.\s+(.*)$")


def _clean_inline(text: str) -> str:
    text = _INLINE_LINK.sub(r"\1", text.strip())
    text = text.replace("**", "").replace("__", "")
    return text.replace("`", "")


def _markdown_blocks(markdown: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    paragraph_lines: list[str] = []

    def flush_paragraph() -> None:
        if paragraph_lines:
            blocks.append(
                (
                    "paragraph",
                    _clean_inline(
                        " ".join(line.strip() for line in paragraph_lines)
                    ),
                )
            )
            paragraph_lines.clear()

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            continue
        if stripped.startswith("# "):
            flush_paragraph()
            blocks.append(("title", _clean_inline(stripped[2:])))
        elif stripped.startswith("## "):
            flush_paragraph()
            blocks.append(("heading1", _clean_inline(stripped[3:])))
        elif stripped.startswith("### "):
            flush_paragraph()
            blocks.append(("heading2", _clean_inline(stripped[4:])))
        elif stripped.startswith("> "):
            flush_paragraph()
            blocks.append(("quote", _clean_inline(stripped[2:])))
        elif stripped.startswith("- "):
            flush_paragraph()
            blocks.append(("bullet", _clean_inline(stripped[2:])))
        elif _NUMBERED_ITEM.match(stripped):
            flush_paragraph()
            match = _NUMBERED_ITEM.match(stripped)
            assert match is not None
            blocks.append(
                (
                    "numbered",
                    f"{match.group(1)}. {_clean_inline(match.group(2))}",
                )
            )
        else:
            paragraph_lines.append(line)
    flush_paragraph()
    return blocks


def _set_run_font(run: Any, name: str, size: float, bold: bool = False) -> None:
    run.font.name = name
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = RGBColor(0, 0, 0)
    r_pr = run._element.get_or_add_rPr()
    r_fonts = r_pr.rFonts
    if r_fonts is None:
        r_fonts = OxmlElement("w:rFonts")
        r_pr.insert(0, r_fonts)
    r_fonts.set(qn("w:ascii"), name)
    r_fonts.set(qn("w:hAnsi"), name)
    r_fonts.set(qn("w:eastAsia"), name)


def _remove_paragraph_borders(paragraph: Any) -> None:
    paragraph_properties = paragraph._p.pPr
    if paragraph_properties is None:
        return
    for border in paragraph_properties.findall(qn("w:pBdr")):
        paragraph_properties.remove(border)


def build_docx(
    markdown: str,
    *,
    fact_bundle: dict[str, Any] | None = None,
    report: ReportDraft | None = None,
) -> bytes:
    document = Document()
    section = document.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(0.8)
    section.bottom_margin = Inches(0.8)
    section.left_margin = Inches(0.9)
    section.right_margin = Inches(0.9)
    styles = document.styles
    normal = styles["Normal"]
    normal.font.name = "Microsoft YaHei"
    normal.font.size = Pt(11)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.25

    for style_name, size in [
        ("Title", 22),
        ("Heading 1", 16),
        ("Heading 2", 13),
    ]:
        style = styles[style_name]
        style.font.name = "Microsoft YaHei"
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor(0, 0, 0)
        style.paragraph_format.space_before = Pt(10)
        style.paragraph_format.space_after = Pt(6)
        style._element.get_or_add_rPr().get_or_add_rFonts().set(
            qn("w:eastAsia"), "Microsoft YaHei"
        )
        if style_name == "Title":
            style_p_pr = style._element.pPr
            if style_p_pr is not None:
                for border in style_p_pr.findall(qn("w:pBdr")):
                    style_p_pr.remove(border)

    has_title = False
    metadata_added = False
    for block_type, text in _markdown_blocks(markdown):
        if block_type == "title":
            paragraph = document.add_paragraph(style="Title")
            _remove_paragraph_borders(paragraph)
            has_title = True
        elif block_type == "heading1":
            paragraph = document.add_paragraph(style="Heading 1")
        elif block_type == "heading2":
            paragraph = document.add_paragraph(style="Heading 2")
        elif block_type == "bullet":
            paragraph = document.add_paragraph(style="List Bullet")
        elif block_type == "numbered":
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.left_indent = Inches(0.25)
        elif block_type == "quote":
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.left_indent = Inches(0.25)
            paragraph.paragraph_format.space_after = Pt(8)
            run = paragraph.add_run(text)
            _set_run_font(run, "Microsoft YaHei", 10)
            run.italic = True
            continue
        else:
            paragraph = document.add_paragraph()
        text_size = {
            "title": 22,
            "heading1": 16,
            "heading2": 13,
        }.get(block_type, 11)
        _set_run_font(
            paragraph.add_run(text),
            "Microsoft YaHei",
            text_size,
            bold=block_type in {"title", "heading1", "heading2"},
        )
        if (
            block_type == "title"
            and fact_bundle
            and report
            and not metadata_added
        ):
            metadata = document.add_paragraph()
            _set_run_font(
                metadata.add_run(
                    f"分析对象：{fact_bundle['player']['name']}　"
                    f"地图：{fact_bundle['match']['map_name']}　"
                    f"报告来源：{report.provider}　"
                    f"导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
                ),
                "Microsoft YaHei",
                9,
            )
            metadata_added = True

    if not has_title:
        paragraph = document.add_paragraph("战术复盘报告", style="Title")
        _remove_paragraph_borders(paragraph)
        _set_run_font(paragraph.runs[0], "Microsoft YaHei", 22, bold=True)

    document.core_properties.title = "CS2 个人战术复盘报告"
    document.core_properties.subject = "基于真实 Demo 事件与证据生成"
    document.core_properties.author = "CS2 Review System"
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _pdf_markup(text: str) -> str:
    return html.escape(text, quote=False).replace("\n", "<br/>")


def build_pdf(
    markdown: str,
    *,
    fact_bundle: dict[str, Any] | None = None,
    report: ReportDraft | None = None,
) -> bytes:
    regular_font_path = Path("C:/Windows/Fonts/Deng.ttf")
    bold_font_path = Path("C:/Windows/Fonts/Dengb.ttf")
    if regular_font_path.is_file():
        font_name = "CS2ReportCN"
        bold_font_name = "CS2ReportCN-Bold"
        pdfmetrics.registerFont(TTFont(font_name, str(regular_font_path)))
        if bold_font_path.is_file():
            pdfmetrics.registerFont(TTFont(bold_font_name, str(bold_font_path)))
        else:
            bold_font_name = font_name
    else:
        font_name = "STSong-Light"
        bold_font_name = font_name
        pdfmetrics.registerFont(UnicodeCIDFont(font_name))
    buffer = io.BytesIO()

    def page_number(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setFont(font_name, 8)
        canvas.setFillColor(colors.HexColor("#555555"))
        canvas.drawRightString(
            letter[0] - 0.75 * inch,
            0.45 * inch,
            f"第 {doc.page} 页",
        )
        canvas.restoreState()

    pdf = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.7 * inch,
        title="CS2 个人战术复盘报告",
        author="CS2 Review System",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ChineseTitle",
        parent=styles["Title"],
        fontName=bold_font_name,
        fontSize=21,
        leading=28,
        textColor=colors.black,
        alignment=TA_LEFT,
        spaceAfter=14,
        wordWrap="CJK",
    )
    heading1 = ParagraphStyle(
        "ChineseHeading1",
        parent=styles["Heading1"],
        fontName=bold_font_name,
        fontSize=15,
        leading=21,
        textColor=colors.black,
        spaceBefore=12,
        spaceAfter=7,
        wordWrap="CJK",
    )
    heading2 = ParagraphStyle(
        "ChineseHeading2",
        parent=styles["Heading2"],
        fontName=bold_font_name,
        fontSize=12,
        leading=18,
        textColor=colors.black,
        spaceBefore=8,
        spaceAfter=5,
        wordWrap="CJK",
    )
    body = ParagraphStyle(
        "ChineseBody",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=10.5,
        leading=16,
        textColor=colors.black,
        spaceAfter=6,
        wordWrap="CJK",
    )
    bullet = ParagraphStyle(
        "ChineseBullet",
        parent=body,
        leftIndent=16,
        firstLineIndent=-10,
        bulletIndent=4,
    )
    quote = ParagraphStyle(
        "ChineseQuote",
        parent=body,
        leftIndent=14,
        textColor=colors.HexColor("#444444"),
        fontSize=9.5,
        leading=15,
    )

    story: list[Any] = []
    for block_type, text in _markdown_blocks(markdown):
        markup = _pdf_markup(text)
        if block_type == "title":
            story.append(Paragraph(markup, title_style))
        elif block_type == "heading1":
            story.append(Paragraph(markup, heading1))
        elif block_type == "heading2":
            story.append(Paragraph(markup, heading2))
        elif block_type == "bullet":
            story.append(Paragraph(markup, bullet, bulletText="•"))
        elif block_type == "quote":
            story.append(Paragraph(markup, quote))
        elif block_type == "numbered":
            story.append(Paragraph(markup, bullet))
        else:
            story.append(Paragraph(markup, body))

    if fact_bundle and report:
        story.insert(
            1,
            Paragraph(
                _pdf_markup(
                    f"分析对象：{fact_bundle['player']['name']}　"
                    f"地图：{fact_bundle['match']['map_name']}　"
                    f"报告来源：{report.provider}　"
                    f"导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
                ),
                quote,
            ),
        )
        story.insert(2, Spacer(1, 8))

    pdf.build(story, onFirstPage=page_number, onLaterPages=page_number)
    return buffer.getvalue()

