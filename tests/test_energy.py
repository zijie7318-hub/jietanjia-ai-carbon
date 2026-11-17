"""本地节能方案、阶梯电价与已接入政策规则的离线测试。"""

import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

os.environ["HT_DB_PATH"] = str(Path(tempfile.mkdtemp(prefix="jtc-energy-")) / "records.db")
os.environ["HT_TOKEN_SECRET"] = "test-only-secret-0123456789abcdef0123456789abcdef"

HERE = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(HERE))

import app as app_module  # noqa: E402
import energy_service  # noqa: E402

R = []


def check(name, cond, extra=""):
    R.append(("PASS  " if cond else "FAIL  ") + name + (("  → " + str(extra)) if extra else ""))


client = app_module.app.test_client()

meta = client.get("/api/energy/meta").get_json()
check("元数据可读取", meta.get("success") is True, meta)
check("措施库为 12 项", meta.get("actionCount") == 12, meta.get("actionCount"))
check("已接入政策为 4 条", meta.get("policyCount") == 4, meta.get("policyCount"))
_policy_doc = json.loads((HERE / "catalog" / "policies.json").read_text(encoding="utf-8"))
check("政策库含家电/数码/汽车报废/汽车置换四类",
      {"xa_appliance_trade_in_2026", "xa_digital_device_subsidy_2026",
       "xa_car_scrappage_subsidy_2026", "xa_car_replacement_subsidy_2026"}
      == {item["id"] for item in _policy_doc["policies"]},
      [item["id"] for item in _policy_doc["policies"]])
check("数据不再整体标记为演示", meta.get("isDemo") is False)
check("包含数据来源和边界说明", len(meta.get("disclaimers") or []) >= 3 and meta.get("factorUrl"),
      meta.get("disclaimers"))
check("官方电力碳足迹因子为 0.5777", abs(meta.get("factorKgCo2ePerKwh") - 0.5777) < 1e-9,
      meta.get("factorKgCo2ePerKwh"))
check("陕西阶梯电价包含三档", len(meta.get("tariffTiers") or []) == 3, meta.get("tariffTiers"))
check("政策覆盖明确为西安市", meta.get("policyCoverage") == ["西安市"], meta.get("policyCoverage"))

own_payload = {
    "city": "西安市",
    "housing": "own",
    "residents": 3,
    "monthlyKwh": 240,
    "budget": 8000,
}
r = client.post("/api/energy/plans", json=own_payload)
body = r.get_json() or {}
check("三档方案接口返回 200", r.status_code == 200 and body.get("success"), body.get("error"))
check("规则模式不声称调用 AI", body.get("mode") == "rules", body.get("mode"))
check("返回正好三个档位", [p.get("tier") for p in body.get("plans", [])] == ["light", "balanced", "deep"],
      [p.get("tier") for p in body.get("plans", [])])
check("三档均有名称和措施", all(p.get("name") and p.get("actions") for p in body.get("plans", [])),
      [(p.get("tier"), len(p.get("actions") or [])) for p in body.get("plans", [])])
check("每档最多四项措施", all(1 <= len(p.get("actions") or []) <= 4 for p in body.get("plans", [])),
      [len(p.get("actions") or []) for p in body.get("plans", [])])
check("基准年用电量按 240×12 计算", body["baseline"]["annualKwh"] == 2880.0, body["baseline"])
check("使用用户填写的月用电量", body["baseline"]["isDefault"] is False)
check("所有方案数字非负", all(
    p["upfrontCost"] >= 0 and p["annualKwhSaved"] >= 0 and p["annualMoneySaved"] >= 0
    and p["annualCo2eKg"] >= 0 for p in body["plans"]))
check("方案包含计算假设", all(p.get("notes") for p in body["plans"]),
      [p.get("notes") for p in body["plans"]])
check("方案标记为估算", all(p.get("estimated") is True for p in body["plans"]))
check("减碳量按版本化因子计算",
      abs(body["plans"][0]["annualCo2eKg"] - round(
          body["plans"][0]["annualKwhSaved"] * meta["factorKgCo2ePerKwh"], 1)) <= 0.2,
      body["plans"][0]["annualCo2eKg"])

policies = body.get("policies") or []
related_ids = {p.get("id") for p in policies if p.get("scope") == "related"}
reference_ids = {p.get("id") for p in policies if p.get("scope") == "reference"}
check("西安市设备更新可匹配家电与数码两类政策",
      related_ids == {"xa_appliance_trade_in_2026", "xa_digital_device_subsidy_2026"}, related_ids)
check("汽车补贴作为政策参考展示，不参与方案匹配",
      reference_ids == {"xa_car_scrappage_subsidy_2026", "xa_car_replacement_subsidy_2026"}, reference_ids)
check("全部四类政策均对用户可见", len(policies) == 4, [p.get("id") for p in policies])
check("政策状态为条件待确认", all(p.get("status") == "candidate" for p in policies), policies)
check("政策不再标记为演示", all(p.get("isDemo") is False for p in policies))
check("政策提供官方原文链接", all(p.get("sourceUrl", "").startswith("https://xasswj.xa.gov.cn/") for p in policies),
      [p.get("sourceUrl") for p in policies])
check("政策包含有效期和自动初筛原因", all(p.get("validTo") and p.get("reasons") for p in policies))
check("政策列出仍需人工核实的条件", all(p.get("manualChecks") for p in policies), policies)
check("方案可关联政策", any(p.get("policyIds") for p in body["plans"]),
      [(p["tier"], p["policyIds"]) for p in body["plans"]])

rented = dict(own_payload, housing="rent", city="西安")
rent_body = client.post("/api/energy/plans", json=rented).get_json()
rent_actions = [a for p in rent_body["plans"] for a in p["actions"]]
check("租房方案排除自有住房措施", all(not a.get("requiresOwner") for a in rent_actions),
      [a["name"] for a in rent_actions if a.get("requiresOwner")])
rent_policies = {p["id"]: p for p in rent_body.get("policies", [])}
check("家电补贴不额外要求自有住房", rent_policies.get("xa_appliance_trade_in_2026", {}).get("eligible") is True,
      rent_policies.get("xa_appliance_trade_in_2026"))
check("租房方案相关与参考政策共四条", set(rent_policies) == {"xa_appliance_trade_in_2026", "xa_digital_device_subsidy_2026", "xa_car_scrappage_subsidy_2026", "xa_car_replacement_subsidy_2026"},
      list(rent_policies))
check("城市简称可匹配西安市政策", "xa_appliance_trade_in_2026" in rent_policies, list(rent_policies))

low_budget = dict(own_payload, budget=50)
low_body = client.post("/api/energy/plans", json=low_budget).get_json()
check("低预算时方案不超预算", all(
    p["upfrontCost"] <= 50 and p["withinBudget"] for p in low_body["plans"]),
    [(p["tier"], p["upfrontCost"], p["withinBudget"]) for p in low_body["plans"]])

zero_budget = dict(own_payload, budget=0)
zero_body = client.post("/api/energy/plans", json=zero_budget).get_json()
check("零预算被原样保留", zero_body["budget"] == 0, zero_body["budget"])
check("零预算不产生付费措施", all(
    p["upfrontCost"] == 0 and p["withinBudget"] for p in zero_body["plans"]),
    [(p["tier"], p["upfrontCost"], p["withinBudget"]) for p in zero_body["plans"]])

bill_payload = {"city": "西安市", "housing": "rent", "residents": 2, "monthlyBill": 110, "tariff": 0.5}
bill_body = client.post("/api/energy/plans", json=bill_payload).get_json()
check("月电费可按电价换算用电量", bill_body["baseline"]["monthlyKwh"] == 220.0, bill_body["baseline"])
check("未填电量时使用填写电价", bill_body["baseline"]["tariff"] == 0.5, bill_body["baseline"])

# 月电费需乘 12 才是年费（历史 bug：只填月电费时年费被算成月费）
bill_only = client.post("/api/energy/plans", json={
    "city": "西安市", "housing": "own", "residents": 3,
    "monthlyBill": 150, "budget": 8000}).get_json()
_b = bill_only["baseline"]
check("只填月电费时年费为月费的12倍",
      abs(_b["annualBill"] - _b["monthlyBill"] * 12) < 0.01,
      {"月费": _b["monthlyBill"], "年费": _b["annualBill"]})
check("只填月电费时年费为1800", abs(_b["annualBill"] - 1800) < 0.01, _b["annualBill"])

abnormal = client.post("/api/energy/plans", json={
    "city": "西安市", "housing": "own", "residents": 3,
    "monthlyKwh": 100, "monthlyBill": 5000, "budget": 8000})
check("电费与电量比例异常被拒绝", abnormal.status_code == 400, abnormal.get_json())

actual_rate = client.post("/api/energy/plans", json={
    "city": "西安市", "housing": "own", "residents": 3,
    "monthlyKwh": 280, "monthlyBill": 160, "budget": 8000}).get_json()
check("电费和电量同填时采用实际平均单价",
      abs(actual_rate["baseline"]["tariff"] - 160 / 280) < 0.0001,
      actual_rate["baseline"])

default_body = client.post("/api/energy/plans", json={
    "city": "西安市", "housing": "own", "residents": 2}).get_json()
check("缺省用电量时明确使用默认基线", default_body["baseline"]["isDefault"] is True,
      default_body["baseline"])
check("默认基线按人口计算", default_body["baseline"]["monthlyKwh"] == 140.0, default_body["baseline"])

for field, value in (("residents", 0), ("residents", "abc"), ("monthlyKwh", 0),
                     ("monthlyKwh", -1), ("budget", -10)):
    bad = dict(own_payload)
    bad[field] = value
    response = client.post("/api/energy/plans", json=bad)
    check("非法输入返回 400：" + field + "=" + str(value), response.status_code == 400,
          response.get_json())

other_body = client.post("/api/energy/plans", json={
    **own_payload, "city": "北京市"}).get_json()
check("其他城市不展示西安政策", other_body.get("policies") == [])
check("其他城市明确提示政策未覆盖", other_body.get("coverage", {}).get("citySupported") is False
      and "仅接入西安市" in other_body.get("coverage", {}).get("message", ""), other_body.get("coverage"))

check("电价按陕西年阶梯估算", 0.49 < body["baseline"]["tariff"] < 0.80
      and body["baseline"]["tariffEstimated"] is True, body["baseline"])

expired = energy_service.match_policies(
    "西安市", "own", ["ac_replace_eff", "fridge_replace_eff"],
    as_of=date(2027, 1, 1))
check("过期政策不判为适用", all(not item["eligible"] and item["status"] == "ineligible" for item in expired),
      expired)

first = client.post("/api/energy/plans", json=own_payload).get_json()
second = client.post("/api/energy/plans", json=own_payload).get_json()
check("同一输入结果可复现", first == second)
try:
    json.dumps(first, allow_nan=False)
    finite = True
except ValueError:
    finite = False
check("响应不含 NaN 或 Infinity", finite)

print("\n".join(R))
passed = sum(1 for item in R if item.startswith("PASS"))
print("\n%d/%d passed" % (passed, len(R)))
sys.exit(0 if passed == len(R) else 1)
