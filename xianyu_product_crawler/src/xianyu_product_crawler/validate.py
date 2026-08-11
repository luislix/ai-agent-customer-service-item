from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class SnapshotValidationError(ValueError):
    pass


def validate_snapshot(raw: Any, *, now: datetime | None = None) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise SnapshotValidationError("记录必须是 JSON object")
    item_id = _required_text(raw, "item_id", 64)
    if not _ID.fullmatch(item_id):
        raise SnapshotValidationError("item_id 只能包含字母、数字、-、_")
    title = _required_text(raw, "title", 200)
    if not title.strip(" .，。！？-_\t\n"):
        raise SnapshotValidationError("title 不能只有标点")
    updated = _time(raw.get("updated_at"))
    current = (now or datetime.now(timezone.utc)).replace(microsecond=0)
    if updated > current.timestamp() + 600:
        raise SnapshotValidationError("updated_at 不能明显晚于当前时间")
    source = raw.get("source_url")
    if not isinstance(source, str) or len(source) > 2048 or not re.fullmatch(r"https?://[^\s]+", source):
        raise SnapshotValidationError("source_url 必须是 http/https URL")
    specifications = _specs(raw.get("specifications", raw.get("specs")))
    pricing = _price(raw.get("pricing", raw.get("price")))
    return {
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
        "source_url": source,
        "updated_at": datetime.fromtimestamp(updated, timezone.utc).isoformat().replace("+00:00", "Z"),
        # Compatibility aliases for the current RAG and older snapshot files.
        "specs": specifications,
        "price": pricing,
    }


def _required_text(raw: dict[str, Any], name: str, limit: int) -> str:
    value = raw.get(name)
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        raise SnapshotValidationError(f"{name} 必填且长度不超过 {limit}")
    return value.strip()


def _optional_text(value: Any, limit: int) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str) or len(value.strip()) > limit:
        raise SnapshotValidationError("文本字段格式或长度非法")
    return value.strip() or None


def _time(value: Any) -> float:
    if not isinstance(value, str):
        raise SnapshotValidationError("updated_at 必须是带时区的 ISO-8601 字符串")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SnapshotValidationError("updated_at 格式非法") from exc
    if parsed.tzinfo is None:
        raise SnapshotValidationError("updated_at 必须带时区")
    return parsed.astimezone(timezone.utc).timestamp()


def _specs(value: Any) -> dict[str, Any] | None:
    if value in (None, {}):
        return None
    if not isinstance(value, dict):
        raise SnapshotValidationError("specs 必须是 object")
    result = {}
    for key, item in value.items():
        if not isinstance(key, str) or not 1 <= len(key.strip()) <= 100:
            raise SnapshotValidationError("规格名称非法")
        if isinstance(item, (str, int, float, bool)):
            result[key.strip()] = item
        elif isinstance(item, list) and all(isinstance(x, (str, int, float, bool)) for x in item):
            result[key.strip()] = list(dict.fromkeys(item))
        else:
            raise SnapshotValidationError("规格值只能是标量或标量数组")
    return result or None


def _included_items(value: Any) -> list[str] | None:
    if value in (None, [], ""):
        return None
    if not isinstance(value, list) or len(value) > 100:
        raise SnapshotValidationError("included_items 必须是最多 100 项的数组")
    result = []
    for item in value:
        if not isinstance(item, str) or not item.strip() or len(item.strip()) > 200:
            raise SnapshotValidationError("included_items 项必须是非空字符串且不超过 200 字符")
        if item.strip() not in result:
            result.append(item.strip())
    return result or None


def _inventory(value: Any) -> dict[str, Any] | None:
    if value in (None, {}):
        return None
    if not isinstance(value, dict) or value.get("status", "unknown") not in {"in_stock", "out_of_stock", "unknown"}:
        raise SnapshotValidationError("inventory 非法")
    quantity = value.get("quantity")
    if quantity is not None and (isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 0):
        raise SnapshotValidationError("inventory.quantity 必须是非负整数")
    return {"status": value.get("status", "unknown"), "quantity": quantity, "note": _optional_text(value.get("note"), 500)}


def _price(value: Any) -> dict[str, Any] | None:
    if value in (None, {}):
        return None
    if not isinstance(value, dict):
        raise SnapshotValidationError("price 必须是 object")
    if value.get("sale_price") in (None, "", "面议"):
        minimum, maximum = value.get("min_price"), value.get("max_price")
        if minimum in (None, "") or maximum in (None, ""):
            return None
        try:
            minimum, maximum = Decimal(str(minimum)), Decimal(str(maximum))
        except (InvalidOperation, TypeError) as exc:
            raise SnapshotValidationError("price.min_price 和 price.max_price 必须是数字") from exc
        if minimum < 0 or maximum < 0 or minimum > maximum:
            raise SnapshotValidationError("价格区间必须是非负且 min_price 不大于 max_price")
        currency = value.get("currency", "CNY")
        if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
            raise SnapshotValidationError("price.currency 必须是三位大写货币代码")
        return {"min_price": str(minimum), "max_price": str(maximum), "currency": currency}
    try:
        amount = Decimal(str(value["sale_price"]))
    except (InvalidOperation, TypeError) as exc:
        raise SnapshotValidationError("price.sale_price 必须是数字") from exc
    if amount < 0:
        raise SnapshotValidationError("price.sale_price 不能小于 0")
    currency = value.get("currency", "CNY")
    if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
        raise SnapshotValidationError("price.currency 必须是三位大写货币代码")
    return {"sale_price": str(amount), "currency": currency}


def _shipping(value: Any) -> dict[str, Any] | None:
    if value in (None, {}):
        return None
    if not isinstance(value, dict):
        raise SnapshotValidationError("shipping 必须是 object")
    hours = value.get("dispatch_sla_hours")
    if hours is not None and (isinstance(hours, bool) or not isinstance(hours, int) or not 0 <= hours <= 720):
        raise SnapshotValidationError("shipping.dispatch_sla_hours 必须在 0-720")
    fee = value.get("fee")
    if fee is not None:
        try:
            fee_decimal = Decimal(str(fee))
        except (InvalidOperation, TypeError) as exc:
            raise SnapshotValidationError("shipping.fee 必须是数字") from exc
        if fee_decimal < 0:
            raise SnapshotValidationError("shipping.fee 不能小于 0")
        fee = str(fee_decimal)
    free_shipping = value.get("free_shipping", False)
    if not isinstance(free_shipping, bool):
        raise SnapshotValidationError("shipping.free_shipping 必须是布尔值")
    return {
        "dispatch_sla_hours": hours,
        "carrier": _optional_text(value.get("carrier"), 100),
        "fee": fee,
        "free_shipping": free_shipping,
        "note": _optional_text(value.get("note"), 500),
    }


def _faq(value: Any) -> list[dict[str, str]] | None:
    if value in (None, []):
        return None
    if not isinstance(value, list) or len(value) > 100:
        raise SnapshotValidationError("faq 必须是最多 100 条的数组")
    result, seen = [], set()
    for row in value:
        if not isinstance(row, dict):
            raise SnapshotValidationError("FAQ 项必须是 object")
        question = _required_text(row, "question", 200)
        answer = _required_text(row, "answer", 1000)
        if len(question) < 2:
            raise SnapshotValidationError("FAQ 问题至少 2 个字符")
        if question.casefold() not in seen:
            result.append({"question": question, "answer": answer})
            seen.add(question.casefold())
    return result or None
