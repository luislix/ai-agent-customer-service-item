"""JSONL 商品快照校验和规范化。"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from .errors import ProductSnapshotValidationError

_ITEM_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_ALLOWED_INVENTORY = {"in_stock", "out_of_stock", "unknown"}


def validate_and_normalize(raw: Any, *, now: datetime | None = None) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ProductSnapshotValidationError("记录必须是 JSON object")
    item_id = _text(raw.get("item_id"), "item_id", 64)
    if not _ITEM_ID_RE.fullmatch(item_id):
        raise ProductSnapshotValidationError("item_id 只能包含字母、数字、-、_，长度 1-64")
    title = _text(raw.get("title"), "title", 200)
    if not title.strip(" .，。！？-_\t\n"):
        raise ProductSnapshotValidationError("title 不能只有标点")
    updated_at = _parse_time(raw.get("updated_at"), "updated_at")
    current = now or datetime.now(timezone.utc)
    if updated_at > current.replace(microsecond=0) + _seconds(600):
        raise ProductSnapshotValidationError("updated_at 不能明显晚于当前时间")
    source_url = _url(raw.get("source_url"))
    specifications = _specs(raw.get("specifications", raw.get("specs")))
    pricing = _price(raw.get("pricing", raw.get("price")))

    result: dict[str, Any] = {
        "item_id": item_id,
        "title": title,
        "description": _optional_text(raw.get("description"), 5000),
        "category": _optional_text(raw.get("category"), 100),
        "condition": _optional_text(raw.get("condition"), 100),
        "specifications": specifications,
        "included_items": _included_items(raw.get("included_items")),
        "inventory": _inventory(raw.get("inventory")),
        "pricing": pricing,
        "shipping": _shipping(raw.get("shipping")),
        "after_sale": _optional_text(raw.get("after_sale"), 2000),
        "faq": _faq(raw.get("faq")),
        "source_url": source_url,
        "updated_at": updated_at.isoformat().replace("+00:00", "Z"),
        "specs": specifications,
        "price": pricing,
    }
    return result


def _text(value: Any, field: str, max_len: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProductSnapshotValidationError(f"{field} 必填且必须是非空字符串")
    value = _strip_markup(value).strip()
    if len(value) > max_len:
        raise ProductSnapshotValidationError(f"{field} 长度不能超过 {max_len}")
    return value


def _optional_text(value: Any, max_len: int) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ProductSnapshotValidationError("文本字段必须是字符串")
    value = _strip_markup(value).strip()
    if len(value) > max_len:
        raise ProductSnapshotValidationError(f"文本长度不能超过 {max_len}")
    return value or None


def _strip_markup(value: str) -> str:
    return re.sub(r"<[^>]*>", "", value)


def _parse_time(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise ProductSnapshotValidationError(f"{field} 必须是带时区的 ISO-8601 字符串")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProductSnapshotValidationError(f"{field} 格式非法") from exc
    if parsed.tzinfo is None:
        raise ProductSnapshotValidationError(f"{field} 必须带时区")
    return parsed.astimezone(timezone.utc).replace(microsecond=0)


def _url(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"https?://[^\s]+", value) or len(value) > 2048:
        raise ProductSnapshotValidationError("source_url 必须是长度不超过 2048 的 http/https URL")
    return value


def _specs(value: Any) -> dict[str, Any] | None:
    if value in (None, {}):
        return None
    if not isinstance(value, dict):
        raise ProductSnapshotValidationError("specs 必须是 object")
    out = {}
    for key, item in value.items():
        if not isinstance(key, str) or not 1 <= len(key.strip()) <= 100:
            raise ProductSnapshotValidationError("规格名称长度必须为 1-100")
        if isinstance(item, (str, int, float, bool)):
            out[key.strip()] = item
        elif isinstance(item, list) and all(isinstance(x, (str, int, float, bool)) for x in item):
            out[key.strip()] = list(dict.fromkeys(item))
        else:
            raise ProductSnapshotValidationError("规格值只能是标量或标量数组")
    return out or None


def _included_items(value: Any) -> list[str] | None:
    if value in (None, [], ""):
        return None
    if not isinstance(value, list) or len(value) > 100:
        raise ProductSnapshotValidationError("included_items 必须是最多 100 项的数组")
    out: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip() or len(item.strip()) > 200:
            raise ProductSnapshotValidationError("included_items 项必须是非空字符串且不超过 200 字符")
        if item.strip() not in out:
            out.append(item.strip())
    return out or None


def _inventory(value: Any) -> dict[str, Any] | None:
    if value in (None, {}):
        return None
    if not isinstance(value, dict):
        raise ProductSnapshotValidationError("inventory 必须是 object")
    status = value.get("status", "unknown")
    if status not in _ALLOWED_INVENTORY:
        raise ProductSnapshotValidationError("inventory.status 非法")
    quantity = value.get("quantity")
    if quantity is not None and (isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 0):
        raise ProductSnapshotValidationError("inventory.quantity 必须是非负整数")
    return {"status": status, "quantity": quantity, "note": _optional_text(value.get("note"), 500)}


def _price(value: Any) -> dict[str, Any] | None:
    if value in (None, {}):
        return None
    if not isinstance(value, dict):
        raise ProductSnapshotValidationError("price 必须是 object")
    amount = value.get("sale_price")
    if amount in (None, "", "面议"):
        minimum, maximum = value.get("min_price"), value.get("max_price")
        if minimum in (None, "") or maximum in (None, ""):
            return None
        try:
            minimum, maximum = Decimal(str(minimum)), Decimal(str(maximum))
        except (InvalidOperation, TypeError) as exc:
            raise ProductSnapshotValidationError("price.min_price 和 price.max_price 必须是数字") from exc
        if minimum < 0 or maximum < 0 or minimum > maximum:
            raise ProductSnapshotValidationError("价格区间必须是非负且 min_price 不大于 max_price")
        currency = value.get("currency", "CNY")
        if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
            raise ProductSnapshotValidationError("price.currency 必须是三位大写货币代码")
        return {"min_price": str(minimum), "max_price": str(maximum), "currency": currency}
    try:
        amount = Decimal(str(amount))
    except (InvalidOperation, TypeError):
        raise ProductSnapshotValidationError("price.sale_price 必须是数字")
    if amount < 0:
        raise ProductSnapshotValidationError("price.sale_price 不能小于 0")
    currency = value.get("currency", "CNY")
    if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
        raise ProductSnapshotValidationError("price.currency 必须是三位大写货币代码")
    return {"sale_price": str(amount), "currency": currency}


def _shipping(value: Any) -> dict[str, Any] | None:
    if value in (None, {}):
        return None
    if not isinstance(value, dict):
        raise ProductSnapshotValidationError("shipping 必须是 object")
    hours = value.get("dispatch_sla_hours")
    if hours is not None and (isinstance(hours, bool) or not isinstance(hours, int) or not 0 <= hours <= 720):
        raise ProductSnapshotValidationError("shipping.dispatch_sla_hours 必须在 0-720")
    fee = value.get("fee")
    if fee is not None:
        try:
            fee = Decimal(str(fee))
        except (InvalidOperation, TypeError):
            raise ProductSnapshotValidationError("shipping.fee 必须是数字")
        if fee < 0:
            raise ProductSnapshotValidationError("shipping.fee 不能小于 0")
        fee = str(fee)
    carrier = _optional_text(value.get("carrier"), 100)
    free_shipping = value.get("free_shipping", False)
    if not isinstance(free_shipping, bool):
        raise ProductSnapshotValidationError("shipping.free_shipping 必须是布尔值")
    return {
        "dispatch_sla_hours": hours,
        "carrier": carrier,
        "fee": fee,
        "free_shipping": free_shipping,
        "note": _optional_text(value.get("note"), 500),
    }


def _faq(value: Any) -> list[dict[str, str]] | None:
    if value in (None, []):
        return None
    if not isinstance(value, list) or len(value) > 100:
        raise ProductSnapshotValidationError("faq 必须是最多 100 条的数组")
    out, seen = [], set()
    for entry in value:
        if not isinstance(entry, dict):
            raise ProductSnapshotValidationError("FAQ 项必须是 object")
        question = _text(entry.get("question"), "faq.question", 200)
        answer = _text(entry.get("answer"), "faq.answer", 1000)
        if len(question) < 2:
            raise ProductSnapshotValidationError("faq.question 至少 2 个字符")
        key = question.casefold()
        if key not in seen:
            out.append({"question": question, "answer": answer})
            seen.add(key)
    return out or None


def _seconds(value: int):
    from datetime import timedelta
    return timedelta(seconds=value)
