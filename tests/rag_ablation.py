#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RAG 检索消融实验：对比「关闭证据包」与「启用条款检索」时模型可用的依据。

这不是模型质量评测。它衡量的是检索层是否真的把可引用、可核对的条款放进了
提示词，以及这些条款是否与当前方案的措施相关。模型是否说得更好，需要真实
模型与人工判定，见文末说明。

用法：
    python tests/rag_ablation.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("HT_DB_PATH", str(Path(tempfile.mkdtemp(prefix="jtc-rag-")) / "r.db"))
os.environ.setdefault("HT_TOKEN_SECRET", "test-only-secret-0123456789abcdef0123456789abcdef")

HERE = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(HERE))

import energy_service  # noqa: E402
import policy_retriever  # noqa: E402

SAMPLES = [
    ("西安自住·3人·280度", {"city": "西安市", "housing": "own", "residents": 3, "monthlyKwh": 280, "budget": 8000}),
    ("西安自住·2人·200度", {"city": "西安市", "housing": "own", "residents": 2, "monthlyKwh": 200, "budget": 3000}),
    ("西安租房·2人·170度", {"city": "西安市", "housing": "rent", "residents": 2, "monthlyKwh": 170, "budget": 1200}),
    ("西安租房·1人·90度", {"city": "西安市", "housing": "rent", "residents": 1, "monthlyKwh": 90, "budget": 500}),
    ("西安自住·4人·360度", {"city": "西安市", "housing": "own", "residents": 4, "monthlyKwh": 360, "budget": 12000}),
    ("西安自住·5人·480度", {"city": "西安市", "housing": "own", "residents": 5, "monthlyKwh": 480, "budget": 15000}),
    ("西安自住·零预算", {"city": "西安市", "housing": "own", "residents": 3, "monthlyKwh": 300, "budget": 0}),
    ("西安租房·零预算", {"city": "西安市", "housing": "rent", "residents": 2, "monthlyKwh": 150, "budget": 0}),
    ("西安自住·只填电费", {"city": "西安市", "housing": "own", "residents": 3, "monthlyBill": 260, "budget": 6000}),
    ("西安自住·只填电量", {"city": "西安市", "housing": "own", "residents": 3, "monthlyKwh": 320, "budget": 6000}),
    ("西安自住·高用电·600度", {"city": "西安市", "housing": "own", "residents": 4, "monthlyKwh": 600, "budget": 20000}),
    ("西安自住·低预算·800元", {"city": "西安市", "housing": "own", "residents": 2, "monthlyKwh": 240, "budget": 800}),
    ("西安租房·1000度", {"city": "西安市", "housing": "rent", "residents": 3, "monthlyKwh": 1000, "budget": 3000}),
    ("西安自住·1人·60度", {"city": "西安市", "housing": "own", "residents": 1, "monthlyKwh": 60, "budget": 2000}),
    ("西安自住·2人·150度", {"city": "西安市", "housing": "own", "residents": 2, "monthlyKwh": 150, "budget": 4000}),
    ("咸阳自住·3人·280度", {"city": "咸阳市", "housing": "own", "residents": 3, "monthlyKwh": 280, "budget": 8000}),
    ("宝鸡租房·2人·180度", {"city": "宝鸡市", "housing": "rent", "residents": 2, "monthlyKwh": 180, "budget": 2000}),
    ("渭南自住·4人·400度", {"city": "渭南市", "housing": "own", "residents": 4, "monthlyKwh": 400, "budget": 10000}),
    ("延安自住·3人·300度", {"city": "延安市", "housing": "own", "residents": 3, "monthlyKwh": 300, "budget": 7000}),
    ("汉中租房·1人·120度", {"city": "汉中市", "housing": "rent", "residents": 1, "monthlyKwh": 120, "budget": 1500}),
    ("榆林自住·5人·520度", {"city": "榆林市", "housing": "own", "residents": 5, "monthlyKwh": 520, "budget": 18000}),
    ("西安自住·3人·260度·低预算", {"city": "西安市", "housing": "own", "residents": 3, "monthlyKwh": 260, "budget": 900}),
    ("西安自住·老人同住·4人·380度", {"city": "西安市", "housing": "own", "residents": 4, "monthlyKwh": 380, "budget": 9000}),
    ("西安租房·合租·3人·220度", {"city": "西安市", "housing": "rent", "residents": 3, "monthlyKwh": 220, "budget": 2500}),
    ("西安自住·2人·210度", {"city": "西安市", "housing": "own", "residents": 2, "monthlyKwh": 210, "budget": 3500}),
    ("西安自住·3人·330度", {"city": "西安市", "housing": "own", "residents": 3, "monthlyKwh": 330, "budget": 5000}),
    ("西安自住·3人·290度·中等预算", {"city": "西安市", "housing": "own", "residents": 3, "monthlyKwh": 290, "budget": 5000}),
    ("西安自住·4人·450度·高预算", {"city": "西安市", "housing": "own", "residents": 4, "monthlyKwh": 450, "budget": 25000}),
    ("西安租房·1人·80度·零预算", {"city": "西安市", "housing": "rent", "residents": 1, "monthlyKwh": 80, "budget": 0}),
    ("西安自住·6人·700度", {"city": "西安市", "housing": "own", "residents": 6, "monthlyKwh": 700, "budget": 30000}),
]


def related_clause(clause: dict, plans: list[dict]) -> bool:
    """条款与当前方案的措施词面有重叠即视为可引用。"""
    action_tokens = set()
    for plan in plans:
        for action in plan.get("actions") or []:
            action_tokens |= set(policy_retriever._tokens(
                "%s %s" % (action.get("name") or "", action.get("category") or "")))
    clause_tokens = set(policy_retriever._tokens(clause.get("text") or ""))
    return bool(action_tokens & clause_tokens)


def main() -> int:
    rows = []
    for label, payload in SAMPLES:
        result = energy_service.build_energy_response(dict(payload))
        plans = result.get("plans") or []
        policies = result.get("policies") or []
        evidence = policy_retriever.retrieve(policies, plans)
        hit = sum(1 for item in evidence if related_clause(item, plans))
        action_count = sum(len(p.get("actions") or []) for p in plans)
        rows.append({
            "label": label,
            "actions": action_count,
            "policies": len(policies),
            "clauses": len(evidence),
            "related": hit,
            "policyIds": len({item.get("policyId") for item in evidence}),
        })

    with_policy = [r for r in rows if r["policies"]]
    total_clauses = sum(r["clauses"] for r in rows)
    total_related = sum(r["related"] for r in rows)
    print("样本数: %d" % len(rows))
    print("命中已接入政策的样本: %d" % len(with_policy))
    print()
    print("%-28s %7s %8s %8s %8s" % ("样本", "措施数", "政策数", "条款数", "相关条款"))
    for r in rows:
        print("%-28s %7d %8d %8d %8d" % (r["label"], r["actions"], r["policies"], r["clauses"], r["related"]))
    print()
    print("=" * 62)
    print("%-22s %14s %14s" % ("指标", "启用检索", "关闭检索"))
    print("%-22s %14s %14s" % ("提示词内条款片段(总计)", total_clauses, 0))
    print("%-22s %14s %14s" % ("可引用政策ID(平均)", "%.2f" % (sum(r["policyIds"] for r in rows) / len(rows)), "0.00"))
    print("%-22s %14s %14s" % ("与措施相关的条款(总计)", total_related, 0))
    print("%-22s %14s %14s" % ("条款相关率", "%.0f%%" % (100.0 * total_related / total_clauses if total_clauses else 0), "—"))
    print()
    print("说明：关闭检索时提示词的「政策证据」为空数组，模型没有任何可引用的条款与政策 ID，")
    print("只能凭先验作答；这一点同时由 tests/test_ai.py 的提示词断言守住。")
    print("本实验不评估模型话术质量；如需真实模型对照，请在有 Key 的环境下单独抽样人工判定。")

    ok = len(with_policy) > 0 and total_clauses > 0 and total_related > 0
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
