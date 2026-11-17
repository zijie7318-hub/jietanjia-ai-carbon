#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 docs/技术报告.md 生成竞赛提交版 docx（含截图、已填团队信息）。

用法：python scripts/build_submission_docx.py
输出：docs/节碳家_技术报告_竞赛提交版.docx
说明：产出唯一提交用 docx，是本仓库的文档定稿来源。
"""

from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
MD = ROOT / "docs" / "技术报告.md"
OUT = ROOT / "docs" / "节碳家_技术报告_竞赛提交版.docx"
IMG_DIR = ROOT / "docs" / "screenshots"


def add_inline(paragraph, text: str):
    """解析 **加粗** 与 `代码`，其余按普通文本写入。"""
    parts = re.split(r"(\*\*[^*]+\*\*|`[^`]+`)", text)
    for part in parts:
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            run = paragraph.add_run(part[2:-2])
            run.bold = True
        elif part.startswith("`") and part.endswith("`"):
            run = paragraph.add_run(part[1:-1])
            run.font.name = "Consolas"
            run.font.size = Pt(9)
        else:
            paragraph.add_run(part)


def main():
    lines = MD.read_text(encoding="utf-8").splitlines()
    doc = Document()

    # 基础样式
    style = doc.styles["Normal"]
    style.font.name = "Microsoft YaHei"
    style.font.size = Pt(10.5)

    i = 0
    in_code = False
    code_buf = []
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # 代码块
        if stripped.startswith("```"):
            if in_code:
                p = doc.add_paragraph()
                p.add_run("\n".join(code_buf)).font.name = "Consolas"
                code_buf = []
                in_code = False
            else:
                in_code = True
            i += 1
            continue
        if in_code:
            code_buf.append(line)
            i += 1
            continue

        # 图片
        m = re.match(r"!\[([^]]*)\]\(([^)]+)\)", stripped)
        if m:
            alt, rel = m.group(1), m.group(2)
            img = IMG_DIR / Path(rel).name
            if img.exists():
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                p.add_run().add_picture(str(img), width=Pt(440))
                cap = doc.add_paragraph()
                cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
                r = cap.add_run(alt)
                r.italic = True
                r.font.size = Pt(9)
                r.font.color.rgb = RGBColor(0x70, 0x85, 0x7A)
            i += 1
            continue

        # 标题
        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            text = stripped.lstrip("# ").strip()
            doc.add_heading(text, level=max(1, min(level, 4)))
            i += 1
            continue

        # 表格（简单解析 markdown 表格）
        if stripped.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|$", lines[i + 1].strip()):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not re.match(r"^[\s:|-]+$", "|".join(cells)):
                    rows.append(cells)
                i += 1
            if rows:
                cols = max(len(r) for r in rows)
                table = doc.add_table(rows=0, cols=cols)
                table.style = "Light Grid Accent 1"
                for ri, row in enumerate(rows):
                    cells = table.add_row().cells
                    for ci in range(cols):
                        val = row[ci] if ci < len(row) else ""
                        val = val.replace("**", "")
                        cells[ci].text = val
                        if ri == 0:
                            for run in cells[ci].paragraphs[0].runs:
                                run.bold = True
            continue

        # 引用
        if stripped.startswith(">"):
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Pt(18)
            add_inline(p, stripped.lstrip("> ").strip())
            i += 1
            continue

        # 列表
        m = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", line)
        if m:
            indent, marker, text = m.groups()
            style_name = "List Number" if marker.endswith(".") else "List Bullet"
            p = doc.add_paragraph(style=style_name)
            if indent:
                p.paragraph_format.left_indent = Pt(18)
            add_inline(p, text)
            i += 1
            continue

        # 空行
        if not stripped:
            i += 1
            continue

        # 普通段落
        p = doc.add_paragraph()
        add_inline(p, stripped)
        i += 1

    doc.save(str(OUT))
    print("已生成：", OUT)
    print("段落数：", len(doc.paragraphs), "| 表格数：", len(doc.tables))


if __name__ == "__main__":
    main()
