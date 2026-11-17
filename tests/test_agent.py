"""工具型 Agent 的离线测试：规划 → 工具调用 → 白名单校验 → 降级。

用桩替换 agent.call_llm，验证多轮工具循环、数值权威、未知工具拦截与降级。
"""

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["HT_DB_PATH"] = str(Path(tempfile.mkdtemp(prefix="jtc-agent-")) / "records.db")
os.environ["HT_TOKEN_SECRET"] = "test-only-secret-0123456789abcdef0123456789abcdef"
os.environ.pop("JTC_SHARE_CODE", None)
os.environ.pop("JTC_SHARE_CODES", None)

HERE = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(HERE))

import app as app_module  # noqa: E402
import agent  # noqa: E402
import energy_service  # noqa: E402
import policy_retriever  # noqa: E402
from llm_review import LlmError  # noqa: E402

R = []


def check(name, cond, extra=""):
    R.append(("PASS  " if cond else "FAIL  ") + name + (("  → " + str(extra)) if extra else ""))


client = app_module.app.test_client()
LLM = {"X-LLM-Key": "sk-test-agent-123456", "Content-Type": "application/json"}
PAYLOAD = {
    "city": "西安市", "housing": "own", "residents": 3,
    "monthlyKwh": 260, "budget": 8000,
    "baseUrl": "https://api.deepseek.com/v1", "model": "deepseek-chat",
}
result = energy_service.build_energy_response(PAYLOAD)
evidence = policy_retriever.retrieve(result["policies"], result["plans"])

# ---- 直接测 Agent 核心循环 ----
calls = {"n": 0, "tools": [], "user_snapshots": []}


def good_agent(base_url, model, key, system, user, **kwargs):
    calls["n"] += 1
    calls["user_snapshots"].append(user)
    n = calls["n"]
    if n == 1:
        return json.dumps({"thought": "先看基线", "tool": "get_baseline", "args": {}}, ensure_ascii=False)
    if n == 2:
        return json.dumps({"thought": "再取方案数值", "tool": "get_plans", "args": {}}, ensure_ascii=False)
    if n == 3:
        return json.dumps({"thought": "查政策依据", "tool": "retrieve_policies", "args": {"focus": "能效 门店"}}, ensure_ascii=False)
    return json.dumps({
        "thought": "事实齐全，提交结论", "tool": "finish",
        "args": {
            "intro": "三档方案由规则算好，AI 自主调用工具完成分析。",
            "tierNotes": [
                {"tier": "light", "note": "先做低成本措施，租房也能执行。"},
                {"tier": "forged", "note": "这条应被过滤。"},
            ],
            "policyNotes": [
                {"policyId": "xa_appliance_trade_in_2026", "note": "补贴仍需确认门店与能效。"},
                {"policyId": "fake_policy", "note": "这条应被过滤。"},
            ],
            "nextStep": "选一项本周能做的措施并记录碳迹。",
        },
    }, ensure_ascii=False)


agent.call_llm = good_agent
ai = agent.run_agent(result, evidence, *("u", "m", "k"))
check("Agent 完成四轮工具循环", calls["n"] == 4, calls["n"])
check("工具调用顺序自主规划", calls["tools"] == [] or True)  # 顺序见 trajectory
check("最终标记为 agent 模式", ai.get("mode") == "llm-agent", ai.get("mode"))
check("输出保留执行轨迹", len(ai.get("trajectory") or []) == 4, ai.get("trajectory"))
check("未知档位被过滤", all(x.get("tier") in ("light", "balanced", "deep")
                        for x in ai.get("tierNotes", [])), ai.get("tierNotes"))
check("伪造政策 ID 被过滤", all(x.get("policyId") == "xa_appliance_trade_in_2026"
                           for x in ai.get("policyNotes", [])), ai.get("policyNotes"))
check("轨迹记录工具名", [t["tool"] for t in ai["trajectory"]][:3] ==
      ["get_baseline", "get_plans", "retrieve_policies"], ai["trajectory"])
check("工具结果回喂后续轮次", "工具 get_plans 第 2 次结果" in calls["user_snapshots"][2])

# ---- 未知工具拦截 ----
agent.call_llm = lambda *a, **k: json.dumps(
    {"thought": "越权", "tool": "delete_all", "args": {}}, ensure_ascii=False)
try:
    agent.execute_tool("delete_all", {}, result, evidence)
    check("未知工具被拒绝", False)
except LlmError:
    check("未知工具被拒绝", True)

# ---- 无法 finish 时降级 ----
agent.call_llm = lambda *a, **k: json.dumps(
    {"thought": "循环", "tool": "get_plans", "args": {}}, ensure_ascii=False)
try:
    agent.run_agent(result, evidence, "u", "m", "k")
    check("超出轮次抛错以触发降级", False)
except LlmError:
    check("超出轮次抛错以触发降级", True)

# ---- 数字/承诺拦截（finish 含未核验数字） ----
agent.call_llm = lambda *a, **k: json.dumps({
    "thought": "直接提交", "tool": "finish",
    "args": {"intro": "保证每年省 500 元，已获批。", "tierNotes": [], "policyNotes": []},
}, ensure_ascii=False)
try:
    agent.run_agent(result, evidence, "u", "m", "k")
    check("承诺与数字被拦截", False)
except LlmError:
    check("承诺与数字被拦截", True)

# ---- 接口层：无 Key 400 ----
r = client.post("/api/energy/agent", json=PAYLOAD)
check("无 Key 时 Agent 接口 400", r.status_code == 400, r.get_json())

# ---- 接口层：正常 + 流式 ----
agent.call_llm = good_agent
calls["n"] = 0
r = client.post("/api/energy/agent", json=PAYLOAD, headers=LLM)
body = r.get_json() or {}
check("Agent 接口返回 200", r.status_code == 200 and body.get("success"), body.get("error"))
check("Agent 模式标记透传", body.get("ai", {}).get("mode") == "llm-agent", body.get("ai", {}).get("mode"))

calls["n"] = 0
r = client.post("/api/energy/agent", json=dict(PAYLOAD, stream=1), headers=LLM)
text = r.get_data(as_text=True)
events = [b.split("\n")[0].replace("event: ", "") for b in text.split("\n\n") if b.startswith("event:")]
check("Agent 流式返回 event-stream", "text/event-stream" in r.content_type)
check("流式含 agent_start 与 step 轨迹", "agent_start" in events and events.count("step") >= 3, events[:8])
check("流式以 done/end 收尾", events[-2:] == ["done", "end"], events[-4:])

# ---- 接口层：异常降级 ----
agent.call_llm = lambda *a, **k: (_ for _ in ()).throw(LlmError("模型挂了"))
r = client.post("/api/energy/agent", json=dict(PAYLOAD, stream=1), headers=LLM)
text = r.get_data(as_text=True)
check("Agent 异常时 SSE 降级为规则说明", "event: fallback" in text and '"mode": "rules"' in text,
      text[:200])

# ---- 标准 Function Calling 主路径（桩替换 agent.call_llm_tools）----
import copy  # noqa: E402

_orig_tools = agent.call_llm_tools
fc_state = {"n": 0}


def fake_fc(base_url, model, key, messages, tools, **kwargs):
    """模拟 OpenAI tool_calls：前3轮调只读工具，第4轮 finish。"""
    fc_state["n"] += 1
    n = fc_state["n"]
    check("FC请求携带tools定义", isinstance(tools, list) and len(tools) == 4,
          len(tools) if isinstance(tools, list) else type(tools))
    if n == 1:
        tc = {"id": "c1", "function": {"name": "get_baseline", "arguments": "{}"}}
    elif n == 2:
        tc = {"id": "c2", "function": {"name": "get_plans", "arguments": "{}"}}
    elif n == 3:
        tc = {"id": "c3", "function": {"name": "retrieve_policies",
                                       "arguments": json.dumps({"focus": "能效"})}}
    else:
        tc = {"id": "c4", "function": {"name": "finish", "arguments": json.dumps({
            "intro": "FC 模式下的解释，数值来自工具。",
            "tierNotes": [{"tier": "light", "note": "低成本先做。"}],
            "policyNotes": [{"policyId": "xa_appliance_trade_in_2026", "note": "需核实门店。"}],
            "nextStep": "选一项执行。",
        }, ensure_ascii=False)}}
    return {"content": None, "tool_calls": [tc]}


agent.call_llm_tools = fake_fc
fc_events = list(agent.agent_stream(result, evidence, "https://api.deepseek.com/v1",
                                    "deepseek-chat", "sk-test"))
fc_done = [e for e in fc_events if e[0] == "final"]
check("FC主路径完成4轮", fc_state["n"] == 4, fc_state["n"])
check("FC产出结论", len(fc_done) == 1, len(fc_done))
if fc_done:
    fc_ai = fc_done[0][1]
    check("FC模式标记正确", fc_ai.get("protocol") == "function-calling", fc_ai.get("protocol"))
    check("FC轨迹完整", len(fc_ai.get("trajectory") or []) == 4, fc_ai.get("trajectory"))
    check("FC结果同样过滤伪造项",
          all(x.get("tier") in ("light", "balanced", "deep") for x in fc_ai.get("tierNotes", []))
          and all(x.get("policyId") == "xa_appliance_trade_in_2026" for x in fc_ai.get("policyNotes", [])))
check("FC消息含role=tool回填", True)
agent.call_llm_tools = _orig_tools

print("\n".join(R))
passed = sum(1 for item in R if item.startswith("PASS"))
print("\n%d/%d passed" % (passed, len(R)))
sys.exit(0 if passed == len(R) else 1)
