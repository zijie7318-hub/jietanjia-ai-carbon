"""电费账单 OCR 的离线测试：数值校验、越界过滤、接口与降级。"""

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["HT_DB_PATH"] = str(Path(tempfile.mkdtemp(prefix="jtc-ocr-")) / "records.db")
os.environ["HT_TOKEN_SECRET"] = "test-only-secret-0123456789abcdef0123456789abcdef"
os.environ.pop("JTC_SHARE_CODE", None)
os.environ.pop("JTC_SHARE_CODES", None)

HERE = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(HERE))

import app as app_module  # noqa: E402
import bill_ocr  # noqa: E402
from llm_review import LlmError  # noqa: E402

R = []


def check(name, cond, extra=""):
    R.append(("PASS  " if cond else "FAIL  ") + name + (("  → " + str(extra)) if extra else ""))


client = app_module.app.test_client()
LLM = {"X-LLM-Key": "sk-test-ocr-123456", "Content-Type": "application/json"}
BASE = {
    "image": "aGVsbG8=", "mime": "image/jpeg",
    "baseUrl": "https://api.deepseek.com/v1", "model": "deepseek-chat",
}

# ---- 模块级：数值校验 ----
fake_ok = lambda *a, **k: json.dumps({
    "monthlyKwh": 260, "monthlyBill": 150, "note": "读到本期电量与电费"}, ensure_ascii=False)
r = bill_ocr.recognize_bill("x", "image/jpeg", "u", "m", "k", call_vision=fake_ok)
check("OCR 正常识别两字段", r["monthlyKwh"] == 260 and r["monthlyBill"] == 150, r)
check("OCR 标记来源可信", r["found"] == {"kwh": True, "bill": True}, r["found"])
check("OCR 带误差提示", "误差" in r["disclaimer"], r["disclaimer"])

fake_over = lambda *a, **k: json.dumps({"monthlyKwh": 999999, "monthlyBill": 150})
r = bill_ocr.recognize_bill("x", "image/jpeg", "u", "m", "k", call_vision=fake_over)
check("OCR 越界用电量被丢弃", r["monthlyKwh"] is None and r["monthlyBill"] == 150, r)

fake_partial = lambda *a, **k: json.dumps({"monthlyKwh": 260, "monthlyBill": None})
r = bill_ocr.recognize_bill("x", "image/jpeg", "u", "m", "k", call_vision=fake_partial)
check("OCR 部分识别可用", r["found"]["kwh"] and not r["found"]["bill"], r)

try:
    bill_ocr.recognize_bill("x", "image/jpeg", "u", "m", "k",
                            call_vision=lambda *a, **k: '{"monthlyKwh":null,"monthlyBill":null}')
    check("OCR 无数字抛错", False)
except LlmError:
    check("OCR 无数字抛错", True)

fake_str = lambda *a, **k: '{"monthlyKwh":"280.5","monthlyBill":"150.2"}'
r = bill_ocr.recognize_bill("x", "image/jpeg", "u", "m", "k", call_vision=fake_str)
check("OCR 字符串数字可解析", r["monthlyKwh"] == 280.5 and r["monthlyBill"] == 150.2, r)

# ---- 接口级 ----
r = client.post("/api/energy/ocr-bill", json=BASE)
check("无 Key 返回 400", r.status_code == 400, r.get_json())

bad = dict(BASE, mime="application/pdf")
r = client.post("/api/energy/ocr-bill", json=bad, headers=LLM)
check("非图片格式被拒", r.status_code == 400, r.get_json())

bad_url = dict(BASE, baseUrl="http://127.0.0.1:9999/v1")
r = client.post("/api/energy/ocr-bill", json=bad_url, headers=LLM)
check("未允许模型地址被拒", r.status_code == 400, r.get_json())

# 用桩替换 app 层引用的 bill_ocr.recognize_bill
_orig = app_module.bill_ocr.recognize_bill
app_module.bill_ocr.recognize_bill = lambda *a, **k: {
    "monthlyKwh": 260, "monthlyBill": 150, "note": "桩", "found": {"kwh": True, "bill": True},
    "disclaimer": "测试"}
r = client.post("/api/energy/ocr-bill", json=BASE, headers=LLM)
body = r.get_json() or {}
check("OCR 接口返回 200", r.status_code == 200 and body.get("success"), body)
check("OCR 接口回传数值", body.get("monthlyKwh") == 260 and body.get("monthlyBill") == 150, body)
app_module.bill_ocr.recognize_bill = _orig

print("\n".join(R))
passed = sum(1 for item in R if item.startswith("PASS"))
print("\n%d/%d passed" % (passed, len(R)))
sys.exit(0 if passed == len(R) else 1)
