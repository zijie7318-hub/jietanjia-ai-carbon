"""AI 解释、政策检索与自动降级的离线测试。"""

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["HT_DB_PATH"] = str(Path(tempfile.mkdtemp(prefix="jtc-ai-")) / "records.db")
os.environ["HT_TOKEN_SECRET"] = "test-only-secret-0123456789abcdef0123456789abcdef"
os.environ.pop("JTC_SHARE_CODE", None)
os.environ.pop("JTC_SHARE_CODES", None)

HERE = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(HERE))

import app as app_module  # noqa: E402
import energy_service  # noqa: E402
import llm_steps  # noqa: E402
import policy_retriever  # noqa: E402

R = []


def check(name, cond, extra=""):
    R.append(("PASS  " if cond else "FAIL  ") + name + (("  → " + str(extra)) if extra else ""))


client = app_module.app.test_client()
LLM = {"X-LLM-Key": "sk-test-ai-123456", "Content-Type": "application/json"}
PAYLOAD = {
    "city": "西安市", "housing": "own", "residents": 3,
    "monthlyKwh": 260, "budget": 8000,
    "baseUrl": "https://api.deepseek.com/v1", "model": "deepseek-chat",
}
result = energy_service.build_energy_response(PAYLOAD)
evidence = policy_retriever.retrieve(result["policies"], result["plans"])
grouped = policy_retriever.group_by_policy(evidence)

check("政策检索返回条款证据", len(evidence) >= 3, len(evidence))
check("检索覆盖当前匹配政策", len(grouped) == len(result["policies"]),
      (len(grouped), len(result["policies"])))
check("每条证据都有政策 ID 和条款", all(x.get("policyId") and x.get("text") for x in evidence))
check("证据保留真实政策状态", all(x.get("isDemo") is False for x in evidence))
check("检索保留官方来源", all(x.get("sourceName") == "西安市商务局" for x in evidence),
      [x.get("sourceName") for x in evidence])

# 无配置与不允许的地址
r = client.post("/api/energy/explain", json=PAYLOAD)
check("无模型 Key 时解释接口返回 400", r.status_code == 400, r.get_json())
bad = dict(PAYLOAD, baseUrl="http://127.0.0.1:8080/v1")
r = client.post("/api/energy/explain", json=bad, headers=LLM)
check("未允许的模型地址被拒绝", r.status_code == 400, r.get_json())

captured = {}


def good_llm(base_url, model, key, system, user, **kwargs):
    captured["system"] = system
    captured["user"] = user
    return json.dumps({
        "intro": "三档方案都已按规则计算，建议先比较投入和回收周期。",
        "tierNotes": [
            {"tier": "light", "note": "先做低成本措施，租房也能执行。"},
            {"tier": "balanced", "note": "在投入和节电之间更均衡。"},
            {"tier": "unknown", "note": "这条应被过滤。"},
        ],
        "policyNotes": [
            {"policyId": "xa_appliance_trade_in_2026", "note": "家电补贴仅表示可能相关，仍需确认门店和能效等级。"},
            {"policyId": "forged_policy", "note": "这条应被过滤。"},
        ],
        "nextStep": "选择一项能本周执行的措施，并记录到碳迹。",
    }, ensure_ascii=False)


llm_steps.call_llm = good_llm
r = client.post("/api/energy/explain", json=PAYLOAD, headers=LLM)
body = r.get_json() or {}
check("模型解释接口返回 200", r.status_code == 200 and body.get("success"), body.get("error"))
check("AI 模式正确标记", body.get("ai", {}).get("mode") == "llm", body.get("ai"))
check("未知档位被过滤", all(x.get("tier") in ("light", "balanced", "deep")
                          for x in body.get("ai", {}).get("tierNotes", [])),
      body.get("ai", {}).get("tierNotes"))
check("伪造政策 ID 被过滤", all(x.get("policyId") == "xa_appliance_trade_in_2026"
                           for x in body.get("ai", {}).get("policyNotes", [])),
      body.get("ai", {}).get("policyNotes"))
check("返回检索元数据", body.get("retrieval", {}).get("clauseCount", 0) > 0,
      body.get("retrieval"))
check("检索模式如实说明", body.get("retrieval", {}).get("mode") == "metadata-filter + local-lexical",
      body.get("retrieval"))
check("提示词包含禁止改数边界", "不能重新计算" in captured.get("system", ""), captured.get("system", "")[:120])
check("提示词只含已匹配的政策证据", "西安市商务局" in captured.get("user", "")
      and "xa_appliance_trade_in_2026" in captured.get("user", ""), captured.get("user", "")[:160])


def garbage_llm(*args, **kwargs):
    return "这不是 JSON"


llm_steps.call_llm = garbage_llm
r = client.post("/api/energy/explain", json=PAYLOAD, headers=LLM)
fallback = r.get_json() or {}
check("模型乱答仍返回 200", r.status_code == 200 and fallback.get("success"), r.status_code)
check("模型乱答自动回退规则解释", fallback.get("ai", {}).get("mode") == "rules", fallback.get("ai"))
check("回退说明保留计算结果", "kWh" in fallback.get("ai", {}).get("intro", ""), fallback.get("ai"))
check("回退说明保留政策边界", any("条件" in x.get("note", "") or "人工确认" in x.get("note", "")
                                for x in fallback.get("ai", {}).get("policyNotes", [])),
      fallback.get("ai", {}).get("policyNotes"))


def boom_llm(*args, **kwargs):
    raise llm_steps.LlmError("上游失败 Authorization=Bearer " + args[2])


llm_steps.call_llm = boom_llm
r = client.post("/api/energy/explain", json=PAYLOAD, headers=LLM)
text = r.get_data(as_text=True)
check("模型异常仍返回可用解释", r.status_code == 200 and (r.get_json() or {}).get("ai"),
      r.status_code)
check("解释错误不泄漏模型 Key", "sk-test-ai-123456" not in text, text[:160])

# 模型地址白名单也应用于原有文案接口
llm_steps.call_llm = good_llm
r = client.post("/api/llm/carbon-feedback", json={
    "text": "今天完成节能行动", "baseUrl": "http://127.0.0.1:9000/v1", "model": "test"
}, headers=LLM)
check("文案接口同样拒绝未允许地址", r.status_code == 400, r.get_json())
check("未使用的任意地址润色接口已移除", client.post(
    "/api/happytime/polish", json={"text": "x", "baseUrl": "http://127.0.0.1:9000/v1", "model": "x"},
    headers=LLM).status_code == 404)

llm_steps.call_llm = lambda *a, **k: '{"intro":"这不是自然语言反馈"}'
try:
    llm_steps.gen_carbon_feedback("测试行动", "计划执行", "https://api.deepseek.com/v1", "m", "sk-x")
    rejected = False
except llm_steps.LlmError:
    rejected = True
check("碳迹反馈拒绝把 JSON 当作日记正文", rejected)

llm_steps.call_llm = lambda *a, **k: "你保证领取补贴，而且一年可以省下 500 元。"
r = client.post("/api/energy/explain", json=PAYLOAD, headers=LLM)
forbidden = r.get_json() or {}
check("保证补贴/数字承诺触发降级", r.status_code == 200
      and forbidden.get("ai", {}).get("mode") == "rules", forbidden.get("ai"))

llm_steps.call_llm = lambda *a, **k: "你已经完成这项节能行动，实际减碳效果很好。"
try:
    llm_steps.gen_carbon_feedback("测试计划", "计划执行",
                                  "https://api.deepseek.com/v1", "m", "sk-x")
    planned_done_rejected = False
except llm_steps.LlmError:
    planned_done_rejected = True
check("计划行动不能被写成已完成", planned_done_rejected)

print("\n".join(R))
passed = sum(1 for item in R if item.startswith("PASS"))
print("\n%d/%d passed" % (passed, len(R)))
sys.exit(0 if passed == len(R) else 1)
