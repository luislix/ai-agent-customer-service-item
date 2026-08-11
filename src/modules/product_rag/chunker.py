"""按商品事实类型切片，保证 chunk 不跨字段、不跨商品。"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta
from typing import Any

from .contracts import KnowledgeChunk

_DYNAMIC_KINDS = {"commercial", "shipping"}


def build_chunks(payload: dict[str, Any], snapshot_id: str, snapshot_hash: str) -> list[KnowledgeChunk]:
    updated_at = datetime.fromisoformat(payload["updated_at"].replace("Z", "+00:00"))
    item_id, title, source = payload["item_id"], payload["title"], payload["source_url"]
    dynamic_until = updated_at + timedelta(hours=24)
    sections: list[tuple[str, str | None, bool]] = [
        ("basic_info", _basic(payload), False),
        ("specification", _specs(payload), False),
        ("commercial", _commercial(payload), True),
        ("shipping", _shipping(payload), True),
        ("after_sale", _after_sale(payload), False),
    ]
    chunks: list[KnowledgeChunk] = []
    index = 0
    for kind, content, dynamic in sections:
        if not content:
            continue
        for part in _split(content):
            chunks.append(_make(item_id, snapshot_id, snapshot_hash, kind, part, dynamic, dynamic_until if dynamic else None, source, updated_at, index))
            index += 1
    for faq in payload.get("faq") or []:
        content = f"商品标题：{title}\n买家问题：{faq['question']}\n标准答案：{faq['answer']}"
        chunks.append(_make(item_id, snapshot_id, snapshot_hash, "faq", content, False, None, source, updated_at, index))
        index += 1
    return chunks


def _basic(p):
    values = [f"商品标题：{p['title']}"]
    if p.get("category"): values.append(f"商品类目：{p['category']}")
    if p.get("condition"): values.append(f"商品成色：{p['condition']}")
    if p.get("description"): values.append(f"商品描述：{p['description']}")
    if p.get("included_items"): values.append(f"商品配件：{'、'.join(p['included_items'])}")
    return "\n".join(values)


def _specs(p):
    if not p.get("specs"): return None
    return "商品标题：%s\n商品规格：\n%s" % (p["title"], "\n".join(f"- {k}：{_value(v)}" for k, v in p["specs"].items()))


def _commercial(p):
    values = [f"商品标题：{p['title']}"]
    if p.get("price"):
        price = p["price"]
        if "sale_price" in price:
            values.append(f"售价：{price['sale_price']} {price['currency']}")
        elif "min_price" in price and "max_price" in price:
            values.append(f"售价区间：{price['min_price']} - {price['max_price']} {price['currency']}")
    inv = p.get("inventory")
    if inv:
        values.append(f"库存状态：{inv['status']}")
        if inv.get("quantity") is not None: values.append(f"库存数量：{inv['quantity']}")
        if inv.get("note"): values.append(f"库存备注：{inv['note']}")
    return "\n".join(values) if len(values) > 1 else None


def _shipping(p):
    s = p.get("shipping")
    if not s: return None
    # 爬虫可能用 fee=0 代表“未采集/默认值”；没有时效、快递或明确非零费用时，
    # 不把它提升为客服可引用的物流事实，避免误报“包邮”。
    if not s.get("free_shipping") and s.get("dispatch_sla_hours") is None and not s.get("carrier") and s.get("fee") in (None, "0", "0.0", "0.00"):
        return None
    values = [f"商品标题：{p['title']}"]
    if s.get("dispatch_sla_hours") is not None: values.append(f"发货时效：{s['dispatch_sla_hours']} 小时内")
    if s.get("carrier"): values.append(f"快递：{s['carrier']}")
    if s.get("free_shipping"): values.append("运费：包邮")
    elif s.get("fee") is not None: values.append(f"运费：{s['fee']}")
    if s.get("note"): values.append(f"物流说明：{s['note']}")
    return "\n".join(values) if len(values) > 1 else None


def _after_sale(p):
    return f"商品标题：{p['title']}\n售后规则：{p['after_sale']}" if p.get("after_sale") else None


def _value(v):
    return "、".join(map(str, v)) if isinstance(v, list) else str(v)


def _split(content: str) -> list[str]:
    if len(content) <= 800: return [content]
    parts, current = [], ""
    for sentence in re.split(r"(?<=[。！？.!?])", content):
        if current and len(current) + len(sentence) > 800:
            parts.append(current)
            current = current[-80:]
        current += sentence
    if current: parts.append(current)
    return parts


def _make(item_id, snapshot_id, snapshot_hash, kind, content, dynamic, valid_until, source, updated_at, index):
    raw = f"{item_id}|{snapshot_hash}|{kind}|{index}|{content}"
    chunk_id = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return KnowledgeChunk(item_id, snapshot_id, chunk_id, kind, content, dynamic, valid_until, source, updated_at)
