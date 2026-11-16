#!/usr/bin/env python3
"""Build the shareable single-file offline demo from the current UI and demo catalog."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "backend/index.html"
BODY = ROOT / "offline/body.html"
APP = ROOT / "offline/app.js"
CATALOG = ROOT / "backend/catalog"
OUTPUT = ROOT / "docs/节碳家_离线演示.html"

CSS = """
.jt-offline-bar{background:var(--red-dark);color:#fff;text-align:center;padding:8px 18px;font-size:12px;line-height:1.55;}
.jt-offline-bar b{color:var(--yellow);}
.offline-pill{cursor:default;background:var(--red-t);color:var(--red-dark);border-color:#B7D9CC;}
@media(max-width:560px){.jt-offline-bar{text-align:left;padding:8px 14px;font-size:11px}}
"""


def main() -> None:
    head = SOURCE.read_text(encoding="utf-8").split("</style>", 1)[0]
    head = re.sub(r"<title>.*?</title>", "<title>节碳家 · 离线交互演示</title>", head)
    head = re.sub(
        r'<meta name="description" content="[^"]*">',
        '<meta name="description" content="节碳家离线交互演示：无需安装或服务器，可直接查看家庭节能方案、政策初筛和碳迹记录。">',
        head,
    )
    head = re.sub(r'<meta name="theme-color" content="[^"]*">',
                  '<meta name="theme-color" content="#0E6E5C">', head)

    app = APP.read_text(encoding="utf-8")
    catalog = {
        "actions": json.loads((CATALOG / "actions.json").read_text(encoding="utf-8")),
        "policies": json.loads((CATALOG / "policies.json").read_text(encoding="utf-8")),
        "factors": json.loads((CATALOG / "factors.json").read_text(encoding="utf-8")),
    }
    app = app.replace(
        "__CATALOG_JSON__",
        json.dumps(catalog, ensure_ascii=False, separators=(",", ":")),
    )
    body = BODY.read_text(encoding="utf-8").replace("__OFFLINE_APP__", app)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(head + CSS + "</style>\n</head>\n" + body, encoding="utf-8")
    print(OUTPUT)
    print("bytes:", OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
