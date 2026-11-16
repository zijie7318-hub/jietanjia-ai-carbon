#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""电费账单 OCR：把账单照片交视觉模型识别成结构化数值。

安全边界：
- 只识别两个字段（月用电量 kWh、月电费 元），其余一律忽略；
- 数值必须在合理区间且为有限数，异常即拒绝；
- 模型只做"读图"，不参与任何节电/减碳计算；
- 结果标注为"待用户确认"，前端填入表单后用户可修改；
- Key 仅单次请求内存使用，不落盘、不写日志。
"""

from __future__ import annotations

import json
import math
import re

from llm_review import LlmError, call_llm_vision, extract_json

PROMPT = (
    "你是一个电费账单读数助手。请仔细看这张电费账单图片，只提取两个字段：\n"
    "1) 本期用电量（单位 kWh/度）\n"
    "2) 本期电费金额（单位 元）\n"
    "只输出 JSON，不要 Markdown 围栏、不要解释：\n"
    '{"monthlyKwh": 数字或null, "monthlyBill": 数字或null, "note": "简短说明读到了什么"}\n'
    "规则：\n"
    "- 只填图片里明确出现的数字，看不清或没有就填 null，绝对不要猜测或推算；\n"
    "- 用电量是电量（kWh/度），电费是金额（元），不要混淆；\n"
    "- 如果有当期与往期多个数字，优先取「本期/本月/本次」；\n"
    "- 数字只写数值本身，不要带单位或逗号。\n"
)


def _valid_number(value, low: float, high: float):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(n) or n < low or n > high:
        return None
    return round(n, 2)


def recognize_bill(image_b64: str, mime: str, base_url: str, model: str,
                   api_key: str, call_vision=None) -> dict:
    """识别账单，返回 {monthlyKwh, monthlyBill, note, found}。异常抛 LlmError。"""
    fn = call_vision or call_llm_vision
    raw = fn(base_url, model, api_key, PROMPT, image_b64, mime or "image/jpeg")
    data = extract_json(raw)

    kwh = _valid_number(data.get("monthlyKwh"), 1, 10000)
    bill = _valid_number(data.get("monthlyBill"), 1, 50000)
    note = str(data.get("note") or "").strip()[:120]

    if kwh is None and bill is None:
        raise LlmError("未能从账单中读到可用的用电量或电费，请手动填写")

    return {
        "monthlyKwh": kwh,
        "monthlyBill": bill,
        "note": note,
        "found": {"kwh": kwh is not None, "bill": bill is not None},
        "disclaimer": "识别结果由 AI 读图得出，可能存在误差，请与账单核对后再生成方案。",
    }
