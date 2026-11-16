#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""节碳家 · 单端口 Flask 应用。

当前阶段只保留可复用底座：静态页面、账号与记录、通用安全中间件和
OpenAI 兼容文案接口。餐饮门店、优惠券、核价与真实下单能力已移除。
"""

from __future__ import annotations

import gzip
import json
import os
import time
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

HERE = Path(__file__).resolve().parent


def _load_dotenv(path: Path) -> None:
    """读取同目录 .env，不覆盖真实环境变量。"""
    if not path.exists():
        return
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val
    except OSError:
        pass


_load_dotenv(HERE / ".env")

import energy_service  # noqa: E402
import policy_retriever  # noqa: E402
from ht_api import ht_bp  # noqa: E402
import ht_api  # noqa: E402
from llm_review import LlmError, MODEL_PRESETS  # noqa: E402
import llm_steps  # noqa: E402
import agent  # noqa: E402  工具型 Agent（新增，原 explain 端点不受影响）

app = Flask(__name__)
app.register_blueprint(ht_bp)

# 默认同源部署；仅在本机跨端口调试时显式开启 CORS。
if (os.environ.get("JTC_ENABLE_CORS") or "").strip().lower() in ("1", "true", "yes"):
    from flask_cors import CORS
    CORS(app)


_COMPRESSIBLE = {"text/html", "text/css", "application/javascript",
                 "text/javascript", "application/json", "image/svg+xml"}


@app.after_request
def _compress(resp):
    """对文本类响应做 gzip，降低首屏传输体积。"""
    if resp.status_code != 200 or resp.headers.get("Content-Encoding"):
        return resp
    if "gzip" not in (request.headers.get("Accept-Encoding") or "").lower():
        return resp
    ctype = (resp.content_type or "").split(";")[0].strip().lower()
    if ctype not in _COMPRESSIBLE:
        return resp
    try:
        if resp.direct_passthrough:
            resp.direct_passthrough = False
        data = resp.get_data()
    except Exception:
        return resp
    if len(data) < 1024:
        return resp
    packed = gzip.compress(data, 6)
    if len(packed) >= len(data):
        return resp
    resp.set_data(packed)
    resp.headers["Content-Encoding"] = "gzip"
    resp.headers["Content-Length"] = str(len(packed))
    resp.headers.add("Vary", "Accept-Encoding")
    return resp


@app.route("/")
def serve_index():
    return send_from_directory(str(HERE), "index.html")


SHARE_CODES = {
    code.strip()
    for code in (os.environ.get("JTC_SHARE_CODES") or os.environ.get("JTC_SHARE_CODE") or "").split(",")
    if code.strip()
}
RATE_LIMIT = int(os.environ.get("JTC_RATE_LIMIT", "40") or 40)
RATE_WINDOW = int(os.environ.get("JTC_RATE_WINDOW", "300") or 300)
TRUST_PROXY = (os.environ.get("JTC_TRUST_PROXY") or "").strip().lower() in ("1", "true", "yes")
_RATE_HITS: dict[str, list[float]] = {}

# 登录接口防止暴力尝试；模型接口防止额度被刷。记录 CRUD 沿用用户令牌隔离。
GUARDED = ("/api/llm/", "/api/energy/", "/api/auth/", "/api/carbon-entries")


def _err(error, code=500):
    return jsonify({"success": False, "error": str(error)}), code


def _client_ip() -> str:
    if TRUST_PROXY:
        forwarded = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        if forwarded:
            return forwarded
    return request.remote_addr or "unknown"


@app.after_request
def _harden(resp):
    """保留原项目的安全响应头和模型 Key 错误脱敏。"""
    if request.path.startswith("/static/"):
        # 静态模块按内容版本变化，允许浏览器缓存；接口响应仍然禁止缓存。
        resp.headers["Cache-Control"] = "public, max-age=3600, must-revalidate"
        resp.headers.add("Vary", "Accept-Encoding")
    else:
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    if resp.mimetype == "text/html":
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "object-src 'none'; base-uri 'none'; form-action 'self'"
        )
    key = (request.headers.get("X-LLM-Key") or "").strip()
    if key and len(key) >= 8 and resp.mimetype in ("application/json", "text/html"):
        try:
            body = resp.get_data(as_text=True)
            if key in body:
                resp.set_data(body.replace(key, "sk-***"))
        except Exception:
            pass
    return resp


@app.before_request
def _guard():
    path = request.path or ""
    if not path.startswith(GUARDED):
        return None
    if SHARE_CODES:
        code = (request.args.get("sharecode") or request.headers.get("X-Share-Code") or "").strip()
        if code not in SHARE_CODES:
            return jsonify({"success": False, "error": "分享码无效，请用本站完整链接打开"}), 403
    if RATE_LIMIT > 0:
        now = time.time()
        ip = _client_ip()
        hits = [stamp for stamp in _RATE_HITS.get(ip, []) if now - stamp < RATE_WINDOW]
        if len(hits) >= RATE_LIMIT:
            return jsonify({"success": False, "error": "请求太频繁了，请稍后再试"}), 429
        hits.append(now)
        _RATE_HITS[ip] = hits
    return None


_LLM_ALLOWED_BASES = {
    preset["baseUrl"].rstrip("/")
    for preset in MODEL_PRESETS
    if preset.get("baseUrl")
}
_LLM_ALLOWED_BASES.update(
    value.strip().rstrip("/")
    for value in (os.environ.get("JTC_LLM_ALLOWED_BASE_URLS") or "").split(",")
    if value.strip()
)


def _llm_args(body):
    """读取 BYOK 配置，并只允许预置或运维显式配置的模型地址。"""
    base_url = str(body.get("baseUrl") or "").strip().rstrip("/")
    model = str(body.get("model") or "").strip()
    key = (request.headers.get("X-LLM-Key") or "").strip()
    if not (base_url and model and key):
        return None
    if base_url not in _LLM_ALLOWED_BASES:
        return None
    return base_url, model, key


@app.route("/api/health")
def health():
    return jsonify({
        "success": True,
        "service": "jie-tan-jia",
        "sharecode_required": bool(SHARE_CODES),
        "share_code_count": len(SHARE_CODES),
        "llm_steps": True,
    })


@app.route("/api/debug/auth")
def debug_auth():
    """仅在 HT_DEBUG=1 时开放，且绝不返回密钥或完整令牌。"""
    if (os.environ.get("HT_DEBUG") or "").strip().lower() not in ("1", "true", "yes"):
        return jsonify({"success": False, "error": "Not Found"}), 404
    raw = (request.headers.get("Authorization") or "").strip()
    bearer = raw.lower().startswith("bearer ")
    user = ht_api._auth() or {}
    try:
        db_path = str(ht_api._db_path())
    except Exception as exc:
        db_path = "unavailable: " + str(exc)[:80]
    return jsonify({
        "success": True,
        "has_authorization": bool(raw),
        "bearer": bearer,
        "has_xht_header": bool(request.headers.get("X-HT-Token")),
        "db_path": db_path,
        "db_error": ht_api._DB_ERROR,
        "user": user.get("username"),
    })


@app.route("/api/energy/meta")
def energy_meta():
    return jsonify({"success": True, **energy_service.get_meta()})


@app.route("/api/energy/plans", methods=["POST"])
def energy_plans():
    """家庭条件 → 三档确定性方案 → 已接入政策候选匹配。"""
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(energy_service.build_energy_response(body))
    except energy_service.EnergyInputError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception:
        app.logger.exception("energy plan failure")
        return jsonify({"success": False, "error": "方案计算失败，请检查输入后重试"}), 500


def _sse(event, payload):
    return "event: %s\ndata: %s\n\n" % (event, json.dumps(payload, ensure_ascii=False))


def _explain_stream(result, evidence, retrieval, llm):
    """SSE 解释流：阶段 → 逐字增量 → 完整校验结果；异常时补发规则说明。"""
    yield _sse("start", {"retrieval": retrieval})
    try:
        for kind, payload in llm_steps.stream_explain(result, evidence, *llm):
            if kind == "done":
                yield _sse("done", {
                    "ai": payload,
                    "aiNote": "AI 解释已生成；数值与资格未由模型决定。",
                    "retrieval": retrieval,
                })
            else:
                yield _sse(kind, payload)
    except LlmError as exc:
        yield _sse("fallback", {
            "ai": energy_service.build_rule_explanation(result),
            "aiNote": "AI 解释暂不可用，已使用规则说明：%s" % str(exc)[:160],
            "retrieval": retrieval,
        })
    except Exception:
        app.logger.exception("energy explanation stream failure")
        yield _sse("fallback", {
            "ai": energy_service.build_rule_explanation(result),
            "aiNote": "AI 解释暂不可用，已使用规则说明。",
            "retrieval": retrieval,
        })
    yield _sse("end", {})


@app.route("/api/energy/explain", methods=["POST"])
def energy_explain():
    """重新计算方案后做本地条款检索，再由模型组织解释；失败自动回退规则说明。"""
    body = request.get_json(silent=True) or {}
    llm = _llm_args(body)
    if not llm:
        return jsonify({
            "success": False,
            "error": "缺少或不受支持的大模型配置，请检查 AI 服务地址后重试",
        }), 400
    try:
        result = energy_service.build_energy_response(body)
    except energy_service.EnergyInputError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400

    evidence = policy_retriever.retrieve(result.get("policies") or [], result.get("plans") or [])
    retrieval = {
        "mode": "metadata-filter + local-lexical",
        "clauseCount": len(evidence),
        "policyCount": len({item.get("policyId") for item in evidence}),
        "coverage": "西安市已接入政策",
    }
    if body.get("stream"):
        return Response(
            _explain_stream(result, evidence, retrieval, llm),
            mimetype="text/event-stream",
            headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"},
        )

    try:
        ai = llm_steps.explain_energy_plan(result, evidence, *llm)
        note = "AI 解释已生成；数值与资格未由模型决定。"
    except LlmError as exc:
        ai = energy_service.build_rule_explanation(result)
        note = "AI 解释暂不可用，已使用规则说明：%s" % str(exc)[:160]
    except Exception:
        app.logger.exception("energy explanation failure")
        ai = energy_service.build_rule_explanation(result)
        note = "AI 解释暂不可用，已使用规则说明。"

    return jsonify({
        "success": True,
        "ai": ai,
        "aiNote": note,
        "retrieval": retrieval,
    })


def _agent_stream(result, evidence, retrieval, llm):
    """Agent SSE：实时逐条推送思考/工具轨迹，结束时给出校验后的解释。"""
    yield _sse("start", {"retrieval": retrieval, "tools": list(agent.TOOL_NAMES)})
    try:
        for kind, payload in agent.agent_stream(result, evidence, *llm):
            if kind == "final":
                yield _sse("done", {
                    "ai": payload,
                    "aiNote": "AI Agent 已调用工具完成分析；全部数值来自规则计算与政策检索，模型未参与计算。",
                    "retrieval": retrieval,
                })
            elif kind == "error":
                yield _sse("fallback", {
                    "ai": energy_service.build_rule_explanation(result),
                    "aiNote": "Agent 暂不可用，已使用规则说明：%s" % str(payload)[:160],
                    "retrieval": retrieval,
                })
            else:
                yield _sse(kind, payload)
    except Exception:
        app.logger.exception("agent stream failure")
        yield _sse("fallback", {
            "ai": energy_service.build_rule_explanation(result),
            "aiNote": "Agent 暂不可用，已使用规则说明。",
            "retrieval": retrieval,
        })
    yield _sse("end", {})


@app.route("/api/energy/agent", methods=["POST"])
def energy_agent():
    """工具型 Agent：模型多轮调用只读工具，数值由规则与 RAG 权威产出。

    与 /api/energy/explain 并存；失败同样降级为规则说明。
    """
    body = request.get_json(silent=True) or {}
    llm = _llm_args(body)
    if not llm:
        return jsonify({
            "success": False,
            "error": "缺少或不受支持的大模型配置，请检查 AI 服务地址后重试",
        }), 400
    try:
        result = energy_service.build_energy_response(body)
    except energy_service.EnergyInputError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400

    evidence = policy_retriever.retrieve(result.get("policies") or [], result.get("plans") or [])
    retrieval = {
        "mode": "agent-tools + metadata-filter + local-lexical",
        "clauseCount": len(evidence),
        "policyCount": len({item.get("policyId") for item in evidence}),
        "coverage": "西安市已接入政策",
    }
    if body.get("stream"):
        return Response(
            _agent_stream(result, evidence, retrieval, llm),
            mimetype="text/event-stream",
            headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"},
        )

    try:
        ai = agent.run_agent(result, evidence, *llm)
        note = "AI Agent 已调用工具完成分析；数值与资格未由模型决定。"
    except LlmError as exc:
        ai = energy_service.build_rule_explanation(result)
        note = "Agent 暂不可用，已使用规则说明：%s" % str(exc)[:160]
    except Exception:
        app.logger.exception("agent failure")
        ai = energy_service.build_rule_explanation(result)
        note = "Agent 暂不可用，已使用规则说明。"

    return jsonify({"success": True, "ai": ai, "aiNote": note, "retrieval": retrieval})


@app.route("/api/llm/carbon-feedback", methods=["POST"])
def llm_carbon_feedback():
    """为碳迹行动生成反馈；失败时由前端回退本地模板。"""
    body = request.get_json(silent=True) or {}
    text = str(body.get("text") or "").strip()
    if not text:
        return jsonify({"success": False, "error": "缺少行动描述"}), 400
    llm = _llm_args(body)
    if not llm:
        return jsonify({"success": False, "error": "缺少大模型配置（baseUrl / model / X-LLM-Key）"}), 400
    try:
        content = llm_steps.gen_carbon_feedback(text, str(body.get("scene") or ""), *llm)
    except LlmError as exc:
        return _err(str(exc), 502)
    return jsonify({"success": True, "content": content, "llm": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
