#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一条命令准备提交材料：重建离线演示、生成报告 HTML、打包源码 ZIP，并跑完全部测试。

设计目标是把交接成本压到最低：接手的人只需要跑这一条命令，然后做一件机器
做不了的事——把 HTML 转成 DOCX。其余路径、排除规则、测试计数都在这里固定。

用法：
    .venv\\Scripts\\python.exe scripts\\prepare_submission.py
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]      # source/maihe-diary
PROJECT = ROOT.parents[1]                        # 项目根目录
HANDOFF = PROJECT / "output" / "handoff"
PY = sys.executable
ZIP_NAME = "第九届传智杯-AI-Web网页赛道-节碳家-源码.zip"


def run(cmd: list[str], cwd: Path, env: dict | None = None) -> str:
    proc = subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        print(proc.stdout[-2000:])
        print(proc.stderr[-2000:])
        raise SystemExit("步骤失败：%s" % " ".join(str(x) for x in cmd))
    return proc.stdout


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=str(ROOT), capture_output=True)
    if out.returncode != 0:
        raise SystemExit("读取 git 文件列表失败")
    return [p for p in out.stdout.decode("utf-8").split("\0") if p]


def build_source_zip(target: Path) -> int:
    files = tracked_files()
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for rel in files:
            src = ROOT / rel
            if src.is_file():
                zf.write(src, rel)
    return len(files)


def suite(label: str, cmd: list[str], cwd: Path) -> str:
    out = run(cmd, cwd)
    match = re.search(r"(\d+)/(\d+) passed", out)
    if not match:
        raise SystemExit("%s 未输出测试结果" % label)
    passed, total = match.group(1), match.group(2)
    print("  %-12s %s/%s" % (label, passed, total))
    return out


def main() -> int:
    HANDOFF.mkdir(parents=True, exist_ok=True)
    print("[1/4] 重建离线演示页")
    run([PY, str(ROOT / "scripts" / "build_offline_demo.py")], ROOT)

    print("[2/4] 生成技术报告 HTML")
    builder = PROJECT / ".workbuddy" / "build" / "build_report_html.py"
    if not builder.exists():
        raise SystemExit("找不到报告构建脚本：%s" % builder)
    env = dict(os.environ, JTC_REPORT_ROOT=str(PROJECT))
    run([PY, str(builder)], PROJECT, env)
    report_html = PROJECT / "output" / "jietanjia-docx-20261116" / "stage2" / "formatted-节碳家技术报告.html"

    print("[3/4] 打包源码 ZIP")
    zip_path = HANDOFF / ZIP_NAME
    count = build_source_zip(zip_path)
    print("  %s（%d 个文件，%.1f KB）" % (zip_path.name, count, zip_path.stat().st_size / 1024))

    print("[4/4] 运行全部离线测试")
    a = suite("smoke_api", [PY, "tests/smoke_api.py"], ROOT)
    b = suite("test_energy", [PY, "tests/test_energy.py"], ROOT)
    c = suite("test_ai", [PY, "tests/test_ai.py"], ROOT)
    d = suite("smoke_ui", ["node", "tests/smoke_ui.js"], ROOT)
    total = sum(int(re.search(r"(\d+)/(\d+) passed", o).group(2)) for o in (a, b, c, d))
    passed = sum(int(re.search(r"(\d+)/(\d+) passed", o).group(1)) for o in (a, b, c, d))
    print("  合计 %d/%d" % (passed, total))

    print("\n完成。产物：")
    print("  离线演示  docs/节碳家_离线演示.html（%.1f KB）"
          % ((ROOT / "docs" / "节碳家_离线演示.html").stat().st_size / 1024))
    print("  报告 HTML %s" % report_html)
    print("  源码 ZIP  %s" % zip_path)
    print("\n还剩一件机器做不了的事：把报告 HTML 转成 DOCX，覆盖")
    print("  docs/节碳家_技术报告_数据来源版.docx")
    print("  deliverables/节碳家_技术报告_数据来源版.docx")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
