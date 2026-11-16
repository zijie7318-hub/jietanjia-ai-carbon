#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""节碳家本地领域服务：家庭输入校验、三档方案、政策初筛。

边界：
- 所有数值由版本化 JSON 参数和确定性公式计算；
- 不调用模型、不访问网络；
- 政策结果只代表“已接入政策的候选匹配”，不代表获批或已具备申领资格。
"""

from __future__ import annotations

import json
import math
import re
from copy import deepcopy
from datetime import date
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
CATALOG_DIR = HERE / "catalog"

TIERS = (
    {"id": "light", "name": "轻量起步", "tagline": "低投入、租房友好，先做马上能做的"},
    {"id": "balanced", "name": "均衡优选", "tagline": "投入与节电更平衡，适合多数家庭"},
    {"id": "deep", "name": "深度减碳", "tagline": "适合自有住房和长期改善"},
)

_HOUSING = {
    "own": "own", "owned": "own", "自有": "own", "自住": "own", "自有住房": "own",
    "rent": "rent", "rented": "rent", "租住": "rent", "租房": "rent",
    "other": "other", "其他": "other",
}


class EnergyInputError(ValueError):
    """用户输入不合法，可安全返回给前端。"""


@lru_cache(maxsize=1)
def _load_catalog():
    with (CATALOG_DIR / "actions.json").open(encoding="utf-8") as fp:
        actions_doc = json.load(fp)
    with (CATALOG_DIR / "policies.json").open(encoding="utf-8") as fp:
        policies_doc = json.load(fp)
    with (CATALOG_DIR / "factors.json").open(encoding="utf-8") as fp:
        factors = json.load(fp)

    actions = actions_doc.get("actions") or []
    if not actions:
        raise RuntimeError("节能措施库为空")
    known = {str(item.get("id")) for item in actions}
    if len(known) != len(actions):
        raise RuntimeError("节能措施 ID 存在重复")

    policies = policies_doc.get("policies") or []
    for policy in policies:
        unknown = [action_id for action_id in policy.get("action_ids", []) if action_id not in known]
        if unknown:
            raise RuntimeError("政策 %s 引用了未知措施：%s" % (policy.get("id"), unknown))

    return actions_doc, policies_doc, factors, {str(item["id"]): item for item in actions}


def _num(value, field: str, low: float, high: float, default=None, required=False):
    if value is None or value == "":
        if required:
            raise EnergyInputError("请填写%s" % field)
        return default
    if isinstance(value, bool):
        raise EnergyInputError("%s必须是数字" % field)
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise EnergyInputError("%s必须是数字" % field)
    if not math.isfinite(number):
        raise EnergyInputError("%s必须是有限数字" % field)
    if number < low or number > high:
        raise EnergyInputError("%s需在 %s 到 %s 之间" % (field, low, high))
    return number


def _norm_region(value: str) -> str:
    text = re.sub(r"\s+", "", str(value or ""))
    return re.sub(r"(特别行政区|自治区|省|市)$", "", text)


def _first_present(mapping: dict, *keys: str):
    """取第一个真正存在的字段；0 是有效输入，不能当成缺省。"""
    for key in keys:
        value = mapping.get(key)
        if value is not None and value != "":
            return value
    return None


def _annual_tier_estimate(annual_kwh: float, profile: dict) -> dict:
    """按陕西年阶梯电价估算年电费、平均电价和最高所处档位。"""
    remaining = max(0.0, annual_kwh)
    lower = 0.0
    total = 0.0
    highest = None
    for tier in profile.get("tiers") or []:
        limit = tier.get("limit_kwh")
        rate = float(tier.get("rate_yuan_per_kwh") or 0)
        upper = float(limit) if limit is not None else remaining + lower
        band = min(remaining, max(0.0, upper - lower))
        if band > 0:
            total += band * rate
            highest = tier
            remaining -= band
        lower = upper
        if remaining <= 0:
            break
    effective = total / annual_kwh if annual_kwh > 0 else float(
        profile.get("reference_rate_yuan_per_kwh") or 0)
    return {
        "annualCost": round(total, 2),
        "effectiveRate": round(effective, 4),
        "tierLabel": (highest or {}).get("label") or "第一档",
    }


def normalize_input(payload: dict) -> dict:
    body = payload if isinstance(payload, dict) else {}
    household = body.get("household") if isinstance(body.get("household"), dict) else body

    city = str(household.get("city") or "西安市").strip()[:30]
    if not city:
        raise EnergyInputError("请选择所在城市")

    housing_raw = str(household.get("housing") or "other").strip().lower()
    housing = _HOUSING.get(housing_raw, _HOUSING.get(str(household.get("housing") or ""), "other"))

    residents = int(_num(household.get("residents"), "家庭人口", 1, 20, 3))
    monthly_kwh = _num(_first_present(household, "monthlyKwh", "monthly_kwh"),
                       "月用电量", 1, 10000, None)
    monthly_bill = _num(_first_present(household, "monthlyBill", "monthly_bill"),
                        "月电费", 1, 50000, None)
    tariff = _num(household.get("tariff"), "电价", 0.1, 2.0, None)
    budget = _num(_first_present(household, "budget", "upfrontBudget", "upfront_budget"),
                  "前期预算", 0, 200000, None)
    return {
        "city": city,
        "housing": housing,
        "residents": residents,
        "monthlyKwh": monthly_kwh,
        "monthlyBill": monthly_bill,
        "tariff": tariff,
        "budget": budget,
    }


def _baseline(household: dict, factors: dict) -> dict:
    profile = factors.get("tariff_profile") or {}
    reference_rate = float(profile.get("reference_rate_yuan_per_kwh") or 0.5483)
    kwh_input = household.get("monthlyKwh")
    bill_input = household.get("monthlyBill")
    tariff_manual = household.get("tariff")

    if tariff_manual is not None and kwh_input is not None:
        monthly_kwh = float(kwh_input)
        tariff = float(tariff_manual)
        tariff_source = "按请求中提供的综合电价计算"
        estimated = False
    elif kwh_input is not None and bill_input is not None:
        monthly_kwh = float(kwh_input)
        tariff = float(bill_input) / monthly_kwh
        if not 0.1 <= tariff <= 2.0:
            raise EnergyInputError("月电费与月用电量比例异常，请检查账单或改用其中一项")
        tariff_source = "按你填写的月电费 ÷ 月用电量计算实际平均单价"
        estimated = False
    elif kwh_input is not None:
        monthly_kwh = float(kwh_input)
        tier = _annual_tier_estimate(monthly_kwh * 12, profile)
        tariff = tier["effectiveRate"]
        tariff_source = "按陕西居民年阶梯电价估算（年化后所处%s）" % tier["tierLabel"]
        estimated = True
    elif bill_input is not None and tariff_manual is not None:
        monthly_kwh = float(bill_input) / float(tariff_manual)
        tariff = float(tariff_manual)
        tariff_source = "按请求中提供的综合电价换算电量"
        estimated = False
    elif bill_input is not None:
        monthly_kwh = float(bill_input) / reference_rate
        tariff = reference_rate
        tariff_source = "仅有月电费，按陕西第二档 %.4f 元/kWh 近似反推用电量" % reference_rate
        estimated = True
    else:
        monthly_kwh = float(household["residents"]) * float(factors["default_monthly_kwh_per_person"])
        tier = _annual_tier_estimate(monthly_kwh * 12, profile)
        tariff = tier["effectiveRate"]
        tariff_source = "无账单数据，按每人每月 %.0f kWh 工程基线及陕西年阶梯电价估算" % float(
            factors["default_monthly_kwh_per_person"])
        estimated = True

    monthly_kwh = round(monthly_kwh, 1)
    annual_kwh = round(monthly_kwh * 12, 1)
    annual_bill = round(float(bill_input), 2) if bill_input is not None else round(monthly_kwh * tariff * 12, 2)
    if kwh_input is not None:
        source = "按你填写的月用电量计算"
    elif bill_input is not None:
        source = "按你填写的月电费反推用电量"
    else:
        source = "未填用电量，按每人每月 %.0f kWh 的工程基线估算" % float(
            factors["default_monthly_kwh_per_person"])
    return {
        "monthlyKwh": monthly_kwh,
        "annualKwh": annual_kwh,
        "tariff": round(tariff, 4),
        "monthlyBill": round(float(bill_input), 2) if bill_input is not None else round(monthly_kwh * tariff, 2),
        "annualBill": annual_bill,
        "source": source,
        "tariffSource": tariff_source,
        "tariffEstimated": estimated,
        "tariffRegion": profile.get("region") or "陕西省",
        "tariffCaveat": profile.get("caveat") or "",
        "isDefault": kwh_input is None and bill_input is None,
    }


def _action_saving(action: dict, baseline: dict) -> float:
    if baseline["monthlyKwh"] < float(action.get("min_monthly_kwh") or 0):
        return 0.0
    if action.get("saving_type") == "percent":
        return baseline["annualKwh"] * float(action.get("saving_value") or 0)
    return float(action.get("saving_value") or 0)


def _eligible(action: dict, household: dict) -> bool:
    if action.get("requires_owner") and household["housing"] != "own":
        return False
    return True


def _action_card(action: dict, household: dict, baseline: dict, factors: dict) -> dict:
    annual_kwh = _action_saving(action, baseline)
    annual_money = annual_kwh * baseline["tariff"]
    upfront = float(action.get("upfront_cost") or 0)
    payback = round(upfront / (annual_money / 12), 1) if annual_money > 0 and upfront > 0 else (
        0.0 if upfront == 0 else None)
    saving_range = action.get("saving_range")
    annual_range = None
    if isinstance(saving_range, list) and len(saving_range) == 2:
        if action.get("saving_type") == "percent":
            annual_range = [round(baseline["annualKwh"] * float(saving_range[0]), 1),
                            round(baseline["annualKwh"] * float(saving_range[1]), 1)]
        else:
            annual_range = [round(float(saving_range[0]), 1), round(float(saving_range[1]), 1)]
    return {
        "id": action["id"],
        "name": action["name"],
        "category": action.get("category"),
        "summary": action.get("summary"),
        "difficulty": action.get("difficulty"),
        "upfrontCost": round(upfront, 2),
        "annualKwhSaved": round(annual_kwh, 1),
        "annualMoneySaved": round(annual_money, 2),
        "annualCo2eKg": round(annual_kwh * float(factors["kg_co2e_per_kwh"]), 1),
        "paybackMonths": payback,
        "requiresOwner": bool(action.get("requires_owner")),
        "needsInstallation": bool(action.get("needs_installation")),
        "assumption": action.get("assumption"),
        "annualKwhRange": annual_range,
        "evidenceLevel": action.get("evidence_level"),
        "evidenceLabel": action.get("evidence_label"),
        "sourceName": action.get("source_name"),
        "sourceUrl": action.get("source_url") or "",
        "sourceNote": action.get("source_note") or action.get("assumption"),
        "costNote": action.get("cost_note"),
    }


def _trim_to_budget(selected: list[dict], budget: float) -> list[dict]:
    kept = list(selected)
    while kept and sum(float(item["upfront_cost"] or 0) for item in kept) > budget:
        removable = [item for item in kept if float(item["upfront_cost"] or 0) > 0]
        if not removable:
            break
        kept.remove(max(removable, key=lambda item: float(item["upfront_cost"] or 0)))
    return kept


def _build_plan(tier: dict, actions: list[dict], household: dict, baseline: dict,
                factors: dict, budget: float) -> dict:
    candidates = [
        action for action in actions
        if tier["id"] in (action.get("tiers") or [])
        and _eligible(action, household)
        and float(action.get("upfront_cost") or 0) <= budget
        and _action_saving(action, baseline) > 0
    ]
    selected = candidates[:4]
    if not selected:
        selected = [
            action for action in actions
            if _eligible(action, household) and _action_saving(action, baseline) > 0
        ][:2]
    selected = _trim_to_budget(selected, budget)

    cards = [_action_card(action, household, baseline, factors) for action in selected]
    overlap = 0.9 if len(cards) > 1 else 1.0
    annual_kwh = sum(card["annualKwhSaved"] for card in cards) * overlap
    annual_money = annual_kwh * baseline["tariff"]
    upfront = sum(card["upfrontCost"] for card in cards)
    payback = round(upfront / (annual_money / 12), 1) if annual_money > 0 and upfront > 0 else (
        0.0 if upfront == 0 else None)

    notes = []
    if len(cards) > 1:
        notes.append("多项措施可能影响同一部分用电，合计已按 10% 重叠折减。")
    if household["housing"] != "own":
        notes.append("已排除需要自有住房或固定施工的措施。")
    if not cards:
        notes.append("当前家庭条件与预算下暂无合适措施，可增加预算或补充用电信息。")

    return {
        "tier": tier["id"],
        "name": tier["name"],
        "tagline": tier["tagline"],
        "actions": cards,
        "actionIds": [card["id"] for card in cards],
        "estimated": True,
        "upfrontCost": round(upfront, 2),
        "annualKwhSaved": round(annual_kwh, 1),
        "annualMoneySaved": round(annual_money, 2),
        "monthlyMoneySaved": round(annual_money / 12, 2),
        "annualCo2eKg": round(annual_kwh * float(factors["kg_co2e_per_kwh"]), 1),
        "paybackMonths": payback,
        "withinBudget": upfront <= budget,
        "notes": notes,
    }


def match_policies(city: str, housing: str, action_ids: list[str],
                   as_of: date | None = None) -> list[dict]:
    """按城市、日期、住房条件和措施做规则初筛，不生成资格结论。"""
    _, policies_doc, _, _ = _load_catalog()
    today = as_of or date.today()
    city_key = _norm_region(city)
    wanted = set(action_ids or [])
    out = []
    for policy in policies_doc.get("policies") or []:
        region = str(policy.get("region") or "")
        if _norm_region(region) != city_key and _norm_region(region) not in ("全国", "全国范围"):
            continue
        related = [action_id for action_id in policy.get("action_ids", []) if action_id in wanted]
        if not related:
            continue

        reasons, eligible = [], True
        start = date.fromisoformat(str(policy["valid_from"]))
        end = date.fromisoformat(str(policy["valid_to"]))
        if today < start:
            eligible = False
            reasons.append("政策尚未到生效日期")
        elif today > end:
            eligible = False
            reasons.append("当前日期不在政策有效期内")
        else:
            reasons.append("当前日期在政策有效期内")

        if policy.get("requires_owner") and housing != "own":
            eligible = False
            reasons.append("该政策要求自有住房")
        elif policy.get("requires_owner"):
            reasons.append("满足自有住房条件")

        out.append({
            "id": policy.get("id"),
            "title": policy.get("title"),
            "region": region,
            "status": "candidate" if eligible else "ineligible",
            "statusLabel": "涉及此政策 · 条件待确认" if eligible else "当前不适用",
            "eligible": eligible,
            "benefit": policy.get("benefit"),
            "benefitRule": deepcopy(policy.get("benefit_rule") or {}),
            "requirements": deepcopy(policy.get("requirements") or []),
            "manualChecks": deepcopy(policy.get("manual_checks") or []),
            "application": policy.get("application"),
            "actionIds": related,
            "reasons": reasons,
            "validFrom": policy.get("valid_from"),
            "validTo": policy.get("valid_to"),
            "isDemo": bool(policy.get("is_demo")),
            "sourceName": policy.get("source_name"),
            "sourceUrl": policy.get("source_url") or "",
            "sourceSecondaryUrl": policy.get("source_secondary_url") or "",
            "sourceRetrievedAt": policy.get("source_retrieved_at"),
            "updatedAt": policy.get("updated_at"),
            "disclaimer": policy.get("disclaimer") or "政策条件仍需用户核实，不代表已获批或可申领。",
        })
    return out


def build_energy_response(payload: dict, as_of: date | None = None) -> dict:
    actions_doc, policies_doc, factors, _ = _load_catalog()
    household = normalize_input(payload)
    baseline = _baseline(household, factors)
    budget = household.get("budget")
    if budget is None:
        budget = float(factors["default_upfront_budget"])

    plans = [
        _build_plan(tier, actions_doc["actions"], household, baseline, factors, budget)
        for tier in TIERS
    ]
    all_action_ids = sorted({action_id for plan in plans for action_id in plan["actionIds"]})
    policies = match_policies(household["city"], household["housing"], all_action_ids, as_of=as_of)
    for plan in plans:
        plan["policyIds"] = [
            policy["id"] for policy in policies
            if set(policy["actionIds"]) & set(plan["actionIds"])
        ]

    tariff_profile = factors.get("tariff_profile") or {}
    supported_regions = list(factors.get("policy_coverage") or [])
    city_supported = any(_norm_region(region) == _norm_region(household["city"])
                         for region in supported_regions)
    if city_supported:
        coverage_message = ("已接入西安市地方政策。政策卡只做候选匹配，能效等级、活动门店和材料条件仍需用户确认。"
                            if policies else "已接入西安市地方政策，但当前方案的措施不属于已收录政策范围。")
    else:
        coverage_message = ("当前仅接入西安市地方政策。该城市不展示地方补贴；未提供实际电费时，电价按陕西参考阶梯估算。")

    return {
        "success": True,
        "mode": "rules",
        "household": household,
        "baseline": baseline,
        "budget": budget,
        "plans": plans,
        "policies": policies,
        "coverage": {
            "citySupported": city_supported,
            "supportedRegions": supported_regions,
            "message": coverage_message,
        },
        "meta": {
            "actionsVersion": actions_doc.get("version"),
            "policiesVersion": policies_doc.get("version"),
            "factorVersion": factors.get("version"),
            "factorKgCo2ePerKwh": factors.get("kg_co2e_per_kwh"),
            "factorSource": factors.get("source"),
            "factorUrl": factors.get("source_url"),
            "factorScope": factors.get("factor_scope"),
            "tariffSource": tariff_profile.get("source"),
            "tariffUrl": tariff_profile.get("source_url"),
            "tariffCaveat": tariff_profile.get("caveat"),
            "policyCoverage": supported_regions,
            "dataClass": factors.get("data_class"),
            "isDemo": False,
            "assumptions": [
                factors.get("disclaimer"),
                actions_doc.get("disclaimer"),
                policies_doc.get("disclaimer"),
                tariff_profile.get("caveat"),
            ],
        },
    }


def build_rule_explanation(result: dict) -> dict:
    """不依赖模型的解释兜底；只转述已计算结果和规则状态。"""
    baseline = result.get("baseline") or {}
    plans = result.get("plans") or []
    policies = result.get("policies") or []
    eligible = [item for item in policies if item.get("eligible")]
    tier_notes = [{
        "tier": plan.get("tier"),
        "note": "%s：包含 %d 项措施，预计年节电约 %.1f kWh，前期投入约 %.2f 元。"
                % (plan.get("name"), len(plan.get("actions") or []),
                   float(plan.get("annualKwhSaved") or 0), float(plan.get("upfrontCost") or 0)),
    } for plan in plans]
    policy_notes = [{
        "policyId": item.get("id"),
        "note": "%s；当前仅完成城市、日期和措施匹配，能效等级、活动门店和材料条件仍需人工确认。"
                % (item.get("benefit") or item.get("title") or "已接入政策"),
    } for item in eligible]
    return {
        "mode": "rules",
        "intro": "已根据月用电基线 %.1f kWh 和当前住房、预算条件完成三档计算。%s；电价口径：%s。"
                 % (float(baseline.get("monthlyKwh") or 0), baseline.get("source") or "",
                    baseline.get("tariffSource") or ""),
        "tierNotes": tier_notes,
        "policyNotes": policy_notes,
        "nextStep": "先比较三档方案的前期投入和回收周期，选择能实际执行的措施，再记录到碳迹日记。",
        "cautions": [
            "节电、费用和减碳量均为估算，不代表实际账单或经核查的减排量。",
            "政策卡只表示可能相关，不代表已获批或可申领。",
        ],
    }


def get_meta() -> dict:
    actions_doc, policies_doc, factors, _ = _load_catalog()
    tariff_profile = factors.get("tariff_profile") or {}
    return {
        "actionsVersion": actions_doc.get("version"),
        "actionCount": len(actions_doc.get("actions") or []),
        "evidenceLevels": sorted({str(item.get("evidence_label")) for item in actions_doc.get("actions") or []}),
        "policiesVersion": policies_doc.get("version"),
        "policyCount": len(policies_doc.get("policies") or []),
        "policyRegion": policies_doc.get("region_scope"),
        "policyCoverage": factors.get("policy_coverage") or [],
        "factorVersion": factors.get("version"),
        "factorKgCo2ePerKwh": factors.get("kg_co2e_per_kwh"),
        "factorSource": factors.get("source"),
        "factorUrl": factors.get("source_url"),
        "tariffRegion": tariff_profile.get("region"),
        "tariffSource": tariff_profile.get("source"),
        "tariffUrl": tariff_profile.get("source_url"),
        "tariffTiers": tariff_profile.get("tiers") or [],
        "isDemo": False,
        "disclaimers": [
            actions_doc.get("disclaimer"),
            policies_doc.get("disclaimer"),
            factors.get("disclaimer"),
            tariff_profile.get("caveat"),
        ],
    }
