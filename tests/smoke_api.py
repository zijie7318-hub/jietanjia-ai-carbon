"""后端离线冒烟测试：通用底座、账号记录、安全边界与模型接口。"""

import json
import os
import sys
import tempfile
from pathlib import Path

TMP_DB = Path(tempfile.mkdtemp(prefix="jtc-test-")) / "records.db"
os.environ["HT_DB_PATH"] = str(TMP_DB)
os.environ["HT_TOKEN_SECRET"] = "test-only-secret-0123456789abcdef0123456789abcdef"
os.environ.pop("JTC_SHARE_CODE", None)
os.environ.pop("JTC_SHARE_CODES", None)
os.environ.pop("HT_DEBUG", None)

HERE = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(HERE))

import app as app_module  # noqa: E402
import llm_steps  # noqa: E402

R = []


def check(name, cond, extra=""):
    R.append(("PASS  " if cond else "FAIL  ") + name + (("  → " + str(extra)) if extra else ""))


def headers(token=""):
    return {"X-HT-Token": token} if token else {}


client = app_module.app.test_client()
LLM = {"X-LLM-Key": "sk-test-123"}
LLM_BODY = {"baseUrl": "https://api.deepseek.com/v1", "model": "deepseek-chat"}

# 配置与基础安全
h = client.get("/api/health")
health = h.get_json()
check("health 可访问", h.status_code == 200 and health.get("success") is True, health)
check("health 不回显密钥", "token" not in json.dumps(health).lower(), health)
check("分享码默认关闭", health.get("sharecode_required") is False)
check("响应禁止缓存", "no-store" in (h.headers.get("Cache-Control") or ""))
check("禁止 iframe 嵌入", h.headers.get("X-Frame-Options") == "DENY")
check("nosniff", h.headers.get("X-Content-Type-Options") == "nosniff")
check("首页带 CSP", "default-src 'self'" in (client.get("/").headers.get("Content-Security-Policy") or ""))
check("调试账户接口默认关闭", client.get("/api/debug/auth").status_code == 404)

# 已移除的餐饮与下单接口
for path in ("/api/stores", "/api/plans", "/api/plans/llm", "/api/blindbox"):
    check("餐饮接口已下线 " + path, client.get(path).status_code == 404)
check("真实下单接口已下线", client.post("/api/create-order", json={}).status_code == 404)
check("旧版记录接口已下线", client.get("/api/happytimes").status_code == 404)

# 账号、记录与用户隔离
r = client.post("/api/auth/register", json={"username": "alpha", "password": "secret123"})
a = r.get_json()
check("注册成功", r.status_code == 200 and bool(a.get("token")), a)
alpha_token = a.get("token", "")
check("当前用户可读取", client.get("/api/auth/me", headers=headers(alpha_token)).status_code == 200)
check("错误密码被拒绝", client.post("/api/auth/login", json={
    "username": "alpha", "password": "wrong-pass"}).status_code == 401)

r = client.post("/api/carbon-entries", json={
    "scene": "planned", "inputText": "调高空调温度", "content": "计划完成一项节能行动。"},
    headers=headers(alpha_token))
saved = r.get_json()
check("登录后可保存记录", r.status_code == 200 and saved.get("success"), saved)
record_id = (saved.get("item") or {}).get("id")

items = client.get("/api/carbon-entries", headers=headers(alpha_token)).get_json().get("items", [])
check("记录按用户读取", len(items) == 1 and items[0].get("inputText") == "调高空调温度", items)
check("计划/完成状态原样保存", items[0].get("scene") == "planned", items[0])

b = client.post("/api/auth/register", json={"username": "beta", "password": "secret123"}).get_json()
beta_token = b.get("token", "")
check("第二个账号注册成功", bool(beta_token))
other = client.get("/api/carbon-entries", headers=headers(beta_token)).get_json().get("items", [])
check("用户记录互相隔离", other == [], other)
client.delete("/api/carbon-entries/%s" % record_id, headers=headers(beta_token))
still_there = client.get("/api/carbon-entries", headers=headers(alpha_token)).get_json().get("items", [])
check("不能删除其他用户的记录", len(still_there) == 1, still_there)
check("不能修改其他用户的记录", client.patch(
    "/api/carbon-entries/%s" % record_id, json={"status": "done"},
    headers=headers(beta_token)).status_code == 404)
check("非法状态被拒绝", client.patch(
    "/api/carbon-entries/%s" % record_id, json={"status": "approved"},
    headers=headers(alpha_token)).status_code == 400)
r = client.patch("/api/carbon-entries/%s" % record_id, json={"status": "done"},
                 headers=headers(alpha_token))
check("计划可标记为已完成", r.status_code == 200 and r.get_json().get("status") == "done", r.get_json())
updated = client.get("/api/carbon-entries", headers=headers(alpha_token)).get_json().get("items", [])
check("更新后状态持久化", updated and updated[0].get("scene") == "done", updated)
client.delete("/api/carbon-entries/%s" % record_id, headers=headers(alpha_token))
check("本人可删除记录", client.get("/api/carbon-entries", headers=headers(alpha_token)).get_json().get("items") == [])

check("未登录不能读取记录", client.get("/api/carbon-entries").status_code == 401)
check("登出成功", client.post("/api/auth/logout", headers=headers(alpha_token)).status_code == 200)
check("登出后令牌失效", client.get("/api/auth/me", headers=headers(alpha_token)).status_code == 401)

# 模型文案接口与 Key 脱敏
replies = {"kind": "ok"}


def fake_call_llm(base_url, model, key, system, user, **kwargs):
    if replies["kind"] == "leak":
        raise llm_steps.LlmError("上游报错：Authorization=Bearer " + key)
    return "今天你完成了一项具体的节能行动，省下的电和减少的排放都值得被记录。"


llm_steps.call_llm = fake_call_llm
r = client.post("/api/llm/carbon-feedback", json={"text": "今天调高了空调温度", **LLM_BODY}, headers=LLM)
check("模型文案接口可用", r.status_code == 200 and len(r.get_json().get("content", "")) > 10, r.get_json())
missing_key = client.post("/api/llm/carbon-feedback", json={"text": "测试", **LLM_BODY})
check("缺少模型 Key 返回 400", missing_key.status_code == 400, missing_key.get_json())

leak_key = "sk-leak-test-1234567890"
replies["kind"] = "leak"
r = client.post("/api/llm/carbon-feedback", json={"text": "测试", **LLM_BODY},
                headers={"X-LLM-Key": leak_key})
check("模型报错中的 Key 被抹掉", leak_key not in r.get_data(as_text=True), r.get_data(as_text=True)[:120])
check("模型错误仍可读", r.status_code == 502 and "上游报错" in (r.get_json() or {}).get("error", ""), r.status_code)
replies["kind"] = "ok"

# 分享码与限流
app_module.SHARE_CODES = {"TESTCODE"}
check("分享码开启后无码被拦截", client.post("/api/llm/carbon-feedback", json={
    "text": "测试", **LLM_BODY}, headers=LLM).status_code == 403)
check("分享码错误被拦截", client.post("/api/llm/carbon-feedback?sharecode=WRONG", json={
    "text": "测试", **LLM_BODY}, headers=LLM).status_code == 403)
check("分享码正确可访问", client.post("/api/llm/carbon-feedback?sharecode=TESTCODE", json={
    "text": "测试", **LLM_BODY}, headers=LLM).status_code == 200)
app_module.SHARE_CODES = set()

old_limit = app_module.RATE_LIMIT
app_module.RATE_LIMIT = 2
app_module._RATE_HITS.clear()
codes = [client.post("/api/llm/carbon-feedback", json={"text": "测试", **LLM_BODY},
                     headers=LLM, environ_base={"REMOTE_ADDR": "9.9.9.9"}).status_code
         for _ in range(4)]
app_module.RATE_LIMIT = old_limit
app_module._RATE_HITS.clear()
check("限流超出阈值返回 429", 429 in codes, codes)

print("\n".join(R))
passed = sum(1 for item in R if item.startswith("PASS"))
print("\n%d/%d passed" % (passed, len(R)))
sys.exit(0 if passed == len(R) else 1)
