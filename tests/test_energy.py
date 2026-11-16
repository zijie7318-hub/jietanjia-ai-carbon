"""本地节能方案与演示政策规则的离线测试。"""

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
check("演示政策为 3 条", meta.get("policyCount") == 3, meta.get("policyCount"))
check("数据明确标记为演示", meta.get("isDemo") is True)
check("包含三项数据免责声明", len(meta.get("disclaimers") or []) == 3, meta.get("disclaimers"))

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
check("西安市自有住房可初筛到三条演示政策", len(policies) == 3, policies)
check("政策状态均为规则初筛 likely", all(p.get("status") == "likely" for p in policies), policies)
check("政策全部标注演示", all(p.get("isDemo") is True for p in policies))
check("演示政策不伪造官方链接", all(p.get("sourceUrl") == "" for p in policies))
check("政策包含有效期和资格原因", all(p.get("validTo") and p.get("reasons") for p in policies))
check("方案可关联政策", any(p.get("policyIds") for p in body["plans"]),
      [(p["tier"], p["policyIds"]) for p in body["plans"]])

rented = dict(own_payload, housing="rent", city="西安")
rent_body = client.post("/api/energy/plans", json=rented).get_json()
rent_actions = [a for p in rent_body["plans"] for a in p["actions"]]
check("租房方案排除自有住房措施", all(not a.get("requiresOwner") for a in rent_actions),
      [a["name"] for a in rent_actions if a.get("requiresOwner")])
rent_policies = {p["id"]: p for p in rent_body.get("policies", [])}
check("租房家庭仍可匹配公共节能包", rent_policies.get("demo_energy_kit", {}).get("eligible") is True,
      rent_policies.get("demo_energy_kit"))
check("租房家庭不得通过自有住房补助初筛",
      rent_policies.get("demo_appliance_trade_in", {}).get("eligible") is not True,
      rent_policies.get("demo_appliance_trade_in"))
check("租房方案只展示与措施相关的政策", set(rent_policies) == {"demo_energy_kit", "demo_window_insulation"},
      list(rent_policies))
check("城市简称可匹配", len(rent_policies) == 2, list(rent_policies))

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

check("其他城市不展示西安演示政策", client.post("/api/energy/plans", json={
    **own_payload, "city": "北京市"}).get_json().get("policies") == [])

expired = energy_service.match_policies(
    "西安市", "own", ["ac_replace_eff", "led_bulbs", "window_seal_removable"],
    as_of=date(2027, 1, 1))
check("过期演示政策不判为符合", all(not item["eligible"] and item["status"] == "ineligible" for item in expired),
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
