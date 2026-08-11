from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .models import ItemDetail
from .validate import validate_snapshot


def normalize_detail(detail: ItemDetail, *, updated_at: datetime | None = None) -> dict[str, Any]:
    """只读取授权适配器提供的标准字段，不从描述文本推断商品事实。"""
    payload = detail.payload
    raw = {
        "item_id": detail.item_id,
        "title": payload.get("title"),
        "description": payload.get("description"),
        "category": payload.get("category"),
        "condition": payload.get("condition"),
        "specifications": payload.get("specifications", payload.get("specs")),
        "included_items": payload.get("included_items"),
        "inventory": payload.get("inventory"),
        "pricing": payload.get("pricing", payload.get("price")),
        "shipping": payload.get("shipping"),
        "after_sale": payload.get("after_sale"),
        "faq": payload.get("faq"),
        "source_url": detail.source_url,
        "updated_at": (updated_at or datetime.now(timezone.utc)).isoformat(),
    }
    return validate_snapshot(raw)
