#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通用 OpenAI 兼容模型调用层（纯标准库，BYOK）。

保留原项目验证过的模型预设、超时与异常处理。模型仅用于开放式文本生成
或解释，任何领域金额、节电量与资格判断都由服务端确定性逻辑负责。
API Key 只在单次请求内存中使用，不落盘、不写日志。
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request


class LlmError(RuntimeError):
    """大模型调用失败（网络/鉴权/协议/返回异常）。"""


# 预设模型（OpenAI 兼容）。base_url 统一拼 "/chat/completions"。
MODEL_PRESETS = [
    {"id": "deepseek", "label": "DeepSeek（推荐，便宜）",
     "baseUrl": "https://api.deepseek.com/v1", "model": "deepseek-chat"},
    {"id": "openai", "label": "OpenAI GPT",
     "baseUrl": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
    {"id": "zhipu", "label": "智谱 GLM（有免费档）",
     "baseUrl": "https://open.bigmodel.cn/api/paas/v4", "model": "glm-4-flash"},
    {"id": "moonshot", "label": "Moonshot Kimi",
     "baseUrl": "https://api.moonshot.cn/v1", "model": "moonshot-v1-8k"},
    {"id": "qwen", "label": "通义千问",
     "baseUrl": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen-plus"},
    {"id": "custom", "label": "自定义（填 base_url + 模型名）", "baseUrl": "", "model": ""},
]


def _endpoint(base_url: str) -> str:
    url = (base_url or "").strip().rstrip("/")
    if not url:
        raise LlmError("缺少大模型 base_url")
    if url.endswith("/chat/completions"):
        return url
    return url + "/chat/completions"


def extract_json(text: str) -> dict:
    """从大模型返回里抽 JSON（可能带 ```json 围栏或前后废话），失败降级为 {raw}。"""
    text = (text or "").strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {"raw": text}
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        try:
            data = json.loads(m.group(1))
            return data if isinstance(data, dict) else {"raw": text}
        except json.JSONDecodeError:
            pass
    a, b = text.find("{"), text.rfind("}")
    if a >= 0 and b > a:
        try:
            data = json.loads(text[a:b + 1])
            return data if isinstance(data, dict) else {"raw": text}
        except json.JSONDecodeError:
            pass
    return {"raw": text}


def call_llm_stream(base_url: str, model: str, api_key: str, system: str, user: str,
                    temperature: float = 0.2, timeout: int = 60):
    """流式调用，逐段 yield 文本增量；协议或网络异常统一抛 LlmError。

    只用于「把已算好的结论讲清楚」这类展示场景，业务数值不经过这里。
    """
    if not (api_key or "").strip():
        raise LlmError("缺少大模型 API Key")
    if not (model or "").strip():
        raise LlmError("缺少大模型 model 名称")
    payload = {
        "model": model.strip(),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "stream": True,
    }
    req = urllib.request.Request(
        _endpoint(base_url),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "Authorization": "Bearer " + api_key.strip(),
        },
    )
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:300]
        raise LlmError(f"大模型接口 HTTP {e.code}：{detail}") from e
    except urllib.error.URLError as e:
        raise LlmError(f"大模型网络错误：{e.reason}") from e

    with resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line or not line.startswith("data:"):
                continue
            chunk = line[5:].strip()
            if chunk == "[DONE]":
                break
            try:
                obj = json.loads(chunk)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and obj.get("error"):
                raise LlmError("大模型接口报错：%s" % json.dumps(obj["error"], ensure_ascii=False)[:300])
            try:
                piece = obj["choices"][0]["delta"].get("content")
            except (KeyError, IndexError, TypeError, AttributeError):
                piece = None
            if piece:
                yield piece


def call_llm(base_url: str, model: str, api_key: str, system: str, user: str,
             temperature: float = 0.3, timeout: int = 90) -> str:
    """OpenAI 兼容 chat/completions 非流式调用，返回 message.content 文本。"""
    if not (api_key or "").strip():
        raise LlmError("缺少大模型 API Key")
    if not (model or "").strip():
        raise LlmError("缺少大模型 model 名称")
    payload = {
        "model": model.strip(),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "stream": False,
    }
    req = urllib.request.Request(
        _endpoint(base_url),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": "Bearer " + api_key.strip(),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:300]
        raise LlmError(f"大模型接口 HTTP {e.code}：{detail}") from e
    except urllib.error.URLError as e:
        raise LlmError(f"大模型网络错误：{e.reason}") from e

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise LlmError(f"大模型返回非 JSON：{raw[:200]}")

    if isinstance(data, dict) and data.get("error"):
        raise LlmError(f"大模型接口报错：{json.dumps(data['error'], ensure_ascii=False)[:300]}")
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise LlmError(f"大模型返回结构异常：{raw[:300]}")
    return content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)


def call_llm_tools(base_url: str, model: str, api_key: str, messages: list,
                   tools: list, temperature: float = 0.1, timeout: int = 40) -> dict:
    """OpenAI 兼容 Function Calling：传 tools 定义，返回 message（含 tool_calls）。

    返回结构：{"content": str|None, "tool_calls": [{"name":..,"arguments":dict,"id":..}]}
    协议异常统一抛 LlmError，由上层降级。
    """
    if not (api_key or "").strip() or not (model or "").strip():
        raise LlmError("缺少大模型 API Key 或 model 名称")
    payload = {
        "model": model.strip(),
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "temperature": temperature,
        "stream": False,
    }
    req = urllib.request.Request(
        _endpoint(base_url),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": "Bearer " + api_key.strip(),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:300]
        raise LlmError(f"大模型接口 HTTP {e.code}：{detail}") from e
    except urllib.error.URLError as e:
        raise LlmError(f"大模型网络错误：{e.reason}") from e
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise LlmError(f"大模型返回非 JSON：{raw[:200]}")
    if isinstance(data, dict) and data.get("error"):
        raise LlmError(f"大模型接口报错：{json.dumps(data['error'], ensure_ascii=False)[:300]}")
    try:
        msg = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        raise LlmError(f"大模型返回结构异常：{raw[:300]}")

    calls = []
    for tc in (msg.get("tool_calls") or []):
        fn = (tc.get("function") or {}) if isinstance(tc, dict) else {}
        name = str(fn.get("name") or "")
        args = fn.get("arguments") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        if not isinstance(args, dict):
            args = {}
        calls.append({"id": tc.get("id") or "", "name": name, "arguments": args})
    return {"content": msg.get("content"), "tool_calls": calls}


def call_llm_vision(base_url: str, model: str, api_key: str, prompt: str,
                    image_b64: str, mime: str = "image/jpeg",
                    temperature: float = 0.0, timeout: int = 45) -> str:
    """OpenAI 兼容视觉识别：image_url data URI 传图，返回模型文本。

    用于把电费账单照片识别成结构化数据；Key 仅单次内存使用。
    """
    if not (api_key or "").strip() or not (model or "").strip():
        raise LlmError("缺少大模型 API Key 或 model 名称")
    if not image_b64:
        raise LlmError("缺少图片数据")
    payload = {
        "model": model.strip(),
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {
                    "url": "data:%s;base64,%s" % (mime, image_b64)}},
            ],
        }],
        "temperature": temperature,
        "stream": False,
    }
    req = urllib.request.Request(
        _endpoint(base_url),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": "Bearer " + api_key.strip(),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:300]
        raise LlmError(f"视觉模型 HTTP {e.code}：{detail}") from e
    except urllib.error.URLError as e:
        raise LlmError(f"视觉模型网络错误：{e.reason}") from e
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise LlmError(f"视觉模型返回非 JSON：{raw[:200]}")
    if isinstance(data, dict) and data.get("error"):
        raise LlmError(f"视觉模型报错：{json.dumps(data['error'], ensure_ascii=False)[:300]}")
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise LlmError(f"视觉模型返回结构异常：{raw[:300]}")
    return content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
