"""闲鱼浏览历史商品快照采集。

浏览器只负责发现商品链接；商品事实通过 XianYuApis 的详情接口获取，
并在落盘前经过 product_rag 的快照契约校验。
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import parse_qs, urlparse

from .validator import validate_and_normalize

_ITEM_ID_RE = re.compile(r"(?<![A-Za-z0-9])([0-9]{6,20})(?![A-Za-z0-9])")


@dataclass(frozen=True)
class DiscoveredItem:
    item_id: str
    source_url: str


@dataclass(frozen=True)
class CrawlFailure:
    item_id: str
    stage: str
    error: str


def extract_item_id(value: str) -> str | None:
    """从闲鱼 URL、DOM 文本或裸 item_id 中提取商品 ID。"""
    value = str(value or "").strip()
    if not value:
        return None
    parsed = urlparse(value)
    query = parse_qs(parsed.query)
    for key in ("itemId", "itemid", "id"):
        candidate = (query.get(key) or [""])[0]
        if re.fullmatch(r"[0-9]{6,20}", candidate):
            return candidate
    match = _ITEM_ID_RE.search(value)
    return match.group(1) if match else None


def discover_item_links(hrefs: Iterable[str], *, limit: int = 20) -> list[DiscoveredItem]:
    """从页面链接去重，保持页面出现顺序。"""
    if limit < 1:
        raise ValueError("limit 必须大于 0")
    result: list[DiscoveredItem] = []
    seen: set[str] = set()
    for href in hrefs:
        item_id = extract_item_id(href)
        if not item_id or item_id in seen:
            continue
        parsed = urlparse(str(href))
        source_url = str(href).strip()
        if parsed.scheme not in {"http", "https"}:
            source_url = f"https://www.goofish.com/item?id={item_id}"
        result.append(DiscoveredItem(item_id, source_url))
        seen.add(item_id)
        if len(result) >= limit:
            break
    return result


def load_item_links(path: str | Path, *, limit: int = 20) -> list[DiscoveredItem]:
    """加载每行一个 URL/item_id 的输入文件。"""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return discover_item_links(lines, limit=limit)


def _first(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _extract_specs(item: dict[str, Any]) -> dict[str, Any] | None:
    """从闲鱼 SKU 属性提取可核验规格，不把任意嵌套响应塞进契约。"""
    raw = _first(item, "props", "properties", "specs")
    specs: dict[str, Any] = dict(raw) if isinstance(raw, dict) else {}
    sku_rows = item.get("skuList") or item.get("idleItemSkuList") or []
    if isinstance(sku_rows, dict):
        sku_rows = [sku_rows]
    for sku in sku_rows:
        if not isinstance(sku, dict):
            continue
        for prop in sku.get("propertyList") or []:
            if not isinstance(prop, dict):
                continue
            name = prop.get("propertyText")
            value = prop.get("actualValueText") or prop.get("valueText")
            if isinstance(name, str) and name.strip() and isinstance(value, (str, int, float, bool)):
                key = name.strip()
                existing = specs.get(key)
                values = existing if isinstance(existing, list) else ([existing] if existing is not None else [])
                if value not in values:
                    values.append(value)
                specs[key] = values[0] if len(values) == 1 else values
    return specs or None


def _extract_shipping(item: dict[str, Any]) -> dict[str, Any] | None:
    tags = item.get("priceRelativeTags") or []
    free_shipping = any(isinstance(tag, dict) and tag.get("text") == "包邮" for tag in tags)
    if not free_shipping:
        return None
    return {"dispatch_sla_hours": None, "carrier": None, "fee": "0.00", "free_shipping": True}


def _extract_included_items(item: dict[str, Any]) -> list[str] | None:
    raw = _first(item, "includedItems", "included_items", "packageList", "packingList")
    if isinstance(raw, str):
        values = [part.strip() for part in re.split(r"[,，、;；\\n]", raw) if part.strip()]
    elif isinstance(raw, list):
        values = [str(part).strip() for part in raw if isinstance(part, (str, int, float)) and str(part).strip()]
    else:
        values = []
    return list(dict.fromkeys(values)) or None


def normalize_item_detail(
    item_id: str,
    source_url: str,
    response: dict[str, Any],
    *,
    updated_at: datetime | None = None,
) -> dict[str, Any]:
    """把闲鱼 mtop 详情响应映射为 product snapshot 契约。"""
    data = response.get("data") if isinstance(response, dict) else None
    item = data.get("itemDO") if isinstance(data, dict) else None
    if not isinstance(item, dict):
        raise ValueError("详情响应缺少 data.itemDO，商品可能已下架或登录态失效")
    title = _first(item, "title", "subject")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("详情响应缺少商品标题")
    description = _first(item, "desc", "description", "detail")
    price_value = _first(item, "soldPrice", "price", "defaultPriceValue")
    price: dict[str, Any] | None = None
    if not item.get("defaultPrice") and str(price_value) not in {"", "None", "99999999"}:
        try:
            price = {"sale_price": str(price_value).replace("¥", "").strip(), "currency": "CNY"}
        except (TypeError, ValueError):
            price = None
    inventory = {"status": "unknown", "quantity": None}
    quantity = _first(item, "quantity", "stock", "inventory")
    if isinstance(quantity, int) and quantity >= 0:
        inventory = {"status": "in_stock" if quantity else "out_of_stock", "quantity": quantity}
    specs = _extract_specs(item)
    category = _first(item, "category", "categoryName", "leafCategoryName")
    included_items = _extract_included_items(item)
    condition = _first(item, "condition", "itemCondition")
    payload = {
        "item_id": str(item_id),
        "title": title,
        "description": description if isinstance(description, str) else None,
        "category": category if isinstance(category, str) else None,
        "condition": condition if isinstance(condition, str) else None,
        "specifications": specs,
        "included_items": included_items,
        "inventory": inventory,
        "pricing": price,
        "shipping": _extract_shipping(item),
        "after_sale": None,
        "faq": None,
        "source_url": source_url,
        "updated_at": (updated_at or datetime.now(timezone.utc)).isoformat(),
    }
    return validate_and_normalize(payload)


def render_markdown(records: Iterable[dict[str, Any]], failures: Iterable[CrawlFailure] = ()) -> str:
    rows = list(records)
    errors = list(failures)
    out = ["# 闲鱼商品快照", "", f"共 {len(rows)} 个商品，失败 {len(errors)} 个。", ""]
    for record in rows:
        price = (record.get("price") or {}).get("sale_price", "未知")
        specs = record.get("specs")
        shipping = record.get("shipping")
        out.extend([
            f"## {record['title']}",
            "",
            f"- 商品 ID：`{record['item_id']}`",
            f"- 来源：{record['source_url']}",
            f"- 价格：{price} CNY" if price != "未知" else "- 价格：未知/私聊",
            f"- 规格：{json.dumps(specs, ensure_ascii=False)}" if specs else "- 规格：未提供",
            "- 物流：包邮（发货时效未提供）" if shipping and shipping.get("fee") == "0.00" else "- 物流：未提供",
            f"- 抓取时间：{record['updated_at']}",
            "",
            record.get("description") or "暂无商品描述。",
            "",
        ])
    if errors:
        out.extend(["## 抓取失败", ""])
        out.extend(f"- `{failure.item_id}`（{failure.stage}）：{failure.error}" for failure in errors)
        out.append("")
    return "\n".join(out)


def write_outputs(
    records: Iterable[dict[str, Any]],
    failures: Iterable[CrawlFailure],
    *,
    output: str | Path,
    markdown: str | Path,
    errors: str | Path | None = None,
) -> None:
    records = list(records)
    failures = list(failures)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "".join(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n" for record in records),
        encoding="utf-8",
    )
    markdown_path = Path(markdown)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_markdown(records, failures), encoding="utf-8")
    if errors:
        error_path = Path(errors)
        error_path.parent.mkdir(parents=True, exist_ok=True)
        error_path.write_text(
            "".join(json.dumps(failure.__dict__, ensure_ascii=False) + "\n" for failure in failures),
            encoding="utf-8",
        )


def crawl_details(
    items: Iterable[DiscoveredItem],
    fetch: Callable[[str], dict[str, Any]],
    *,
    delay: float = 0.0,
) -> tuple[list[dict[str, Any]], list[CrawlFailure]]:
    records: list[dict[str, Any]] = []
    failures: list[CrawlFailure] = []
    for item in items:
        try:
            records.append(normalize_item_detail(item.item_id, item.source_url, fetch(item.item_id)))
        except Exception as exc:  # noqa: BLE001 - one bad item must not stop the batch
            failures.append(CrawlFailure(item.item_id, "detail", str(exc)))
        if delay > 0:
            time.sleep(delay)
    return records, failures


def browser_discover(history_url: str, cookie: str, *, limit: int = 20, scrolls: int = 3) -> list[DiscoveredItem]:
    """在已登录浏览器上下文中读取历史页链接；Playwright 为可选依赖。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("浏览器模式需要安装 playwright；可先使用 --from-urls 离线模式") from exc
    cookies = []
    for pair in cookie.split(";"):
        name, sep, value = pair.strip().partition("=")
        if sep and name and value:
            cookies.append({"name": name, "value": value, "domain": ".goofish.com", "path": "/"})
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context()
        if cookies:
            context.add_cookies(cookies)
        page = context.new_page()
        try:
            page.goto(history_url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(800)
            if "/login" in page.url or page.locator("a[href*='/login']").count():
                raise RuntimeError("闲鱼网页端登录态无效；请更新包含网页端会话的 XIANYU_COOKIE")
            for _ in range(max(0, scrolls)):
                page.mouse.wheel(0, 1600)
                page.wait_for_timeout(800)
            hrefs = page.locator("a").evaluate_all("els => els.map(e => e.href).filter(Boolean)")
        finally:
            browser.close()
    return discover_item_links(hrefs, limit=limit)
