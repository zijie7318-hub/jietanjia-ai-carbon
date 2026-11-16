#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""轻量政策条款检索：元数据前置过滤后的本地词法检索。

这里不引入向量数据库。当前政策语料很小，先由规则引擎完成城市、日期、
住房和措施过滤，再按条款与当前措施的词面相关度选出可引用的证据片段。
AI 只能基于这些片段写摘要，不能新增政策或改变资格判断。
"""

from __future__ import annotations

import re
from collections import Counter

_STOP = {"申请", "材料", "相关", "符合", "条件", "政策", "补贴", "当前", "可以", "需要"}


def _tokens(text: str) -> Counter:
    text = str(text or "").lower()
    words = re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]{2,}", text)
    tokens = []
    for word in words:
        if re.fullmatch(r"[\u4e00-\u9fff]+", word):
            tokens.append(word)
            tokens.extend(word[i:i + 2] for i in range(max(0, len(word) - 1)))
        else:
            tokens.append(word)
    return Counter(token for token in tokens if len(token) > 1 and token not in _STOP)


def retrieve(policy_matches: list[dict], plans: list[dict], limit: int = 8) -> list[dict]:
    """返回带政策 ID 的条款证据，按相关度排序并保留来源状态。"""
    action_names = []
    for plan in plans or []:
        for action in plan.get("actions") or []:
            action_names.append(str(action.get("name") or ""))
            action_names.append(str(action.get("category") or ""))
    query = _tokens(" ".join(action_names))

    chunks = []
    for policy in policy_matches or []:
        fields = [
            ("补助内容", policy.get("benefit")),
            ("资格条件", " ".join(policy.get("requirements") or []) + " " + " ".join(policy.get("reasons") or [])),
            ("办理方式", policy.get("application")),
        ]
        for label, text in fields:
            text = str(text or "").strip()
            if not text:
                continue
            overlap = sum(min(count, query.get(token, 0)) for token, count in _tokens(text).items())
            chunks.append({
                "policyId": policy.get("id"),
                "title": policy.get("title"),
                "region": policy.get("region"),
                "status": policy.get("status"),
                "isDemo": bool(policy.get("isDemo")),
                "sourceName": policy.get("sourceName"),
                "sourceUrl": policy.get("sourceUrl") or "",
                "validFrom": policy.get("validFrom"),
                "validTo": policy.get("validTo"),
                "label": label,
                "text": text[:500],
                "score": overlap,
            })
    chunks.sort(key=lambda item: (-item["score"], item["policyId"], item["label"]))
    return chunks[:max(1, limit)]


def group_by_policy(evidence: list[dict]) -> list[dict]:
    """按政策聚合条款，供界面和模型提示词使用。"""
    grouped = {}
    for item in evidence:
        pid = item.get("policyId")
        if pid not in grouped:
            grouped[pid] = {
                "policyId": pid,
                "title": item.get("title"),
                "region": item.get("region"),
                "status": item.get("status"),
                "isDemo": item.get("isDemo"),
                "sourceName": item.get("sourceName"),
                "validFrom": item.get("validFrom"),
                "validTo": item.get("validTo"),
                "clauses": [],
            }
        grouped[pid]["clauses"].append({"label": item.get("label"), "text": item.get("text")})
    return list(grouped.values())
