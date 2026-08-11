"""将本机扩展采集的页面资料转换为可人工审核的商品快照。"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .models import CrawlFailure, ItemDetail
from .normalize import normalize_detail
from .outputs import write_outputs

_ID = re.compile(r"(?<![A-Za-z0-9])([0-9]{6,20})(?![A-Za-z0-9])")


def build_captures(capture_dir: str | Path) -> tuple[list[dict], list[CrawlFailure], list[ItemDetail]]:
    records, failures, details = [], [], []
    seen: set[str] = set()
    for path in sorted(Path(capture_dir).glob("*.json")):
        try:
            capture = json.loads(path.read_text(encoding="utf-8"))
            item_id = extract_item_id(capture)
            if item_id in seen:
                continue
            detail = ItemDetail(item_id, capture["source_url"], _payload(capture))
            records.append(normalize_detail(detail))
            details.append(detail)
            seen.add(item_id)
        except Exception as exc:  # Each local capture is independently reviewable.
            failures.append(CrawlFailure("manual", None, "normalize", f"{path.name}: {exc}"))
    return records, failures, details


def extract_item_id(capture: dict[str, Any]) -> str:
    hint = str(capture.get("item_id_hint") or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", hint):
        return hint
    source = capture.get("source_url")
    if not isinstance(source, str):
        raise ValueError("缺少 source_url")
    query = parse_qs(urlparse(source).query)
    for key in ("itemId", "itemid", "id"):
        value = (query.get(key) or [""])[0]
        if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value):
            return value
    match = _ID.search(source)
    if match:
        return match.group(1)
    raise ValueError("无法从页面 URL 提取 item_id")


def _payload(capture: dict[str, Any]) -> dict[str, Any]:
    visible = capture.get("visible")
    if not isinstance(visible, dict):
        raise ValueError("缺少 visible 页面资料")
    title = visible.get("title")
    if not isinstance(title, str) or _is_generic_page_text(title):
        raise ValueError("页面标题是闲鱼通用内容，未采集到真实商品标题")
    description = visible.get("description")
    if isinstance(description, str) and _is_generic_page_text(description):
        description = None
    return {
        "title": title,
        "description": description,
        "category": visible.get("category"),
        "condition": visible.get("condition"),
        "specifications": visible.get("specifications", visible.get("specs")),
        "included_items": visible.get("included_items"),
        "inventory": visible.get("inventory"),
        "pricing": visible.get("pricing", visible.get("price")),
        "shipping": visible.get("shipping"),
        "after_sale": visible.get("after_sale"),
        "faq": visible.get("faq"),
    }


def _is_generic_page_text(value: str) -> bool:
    text = re.sub(r"\s+", "", value).lower()
    return not text or text == "为你推荐" or text == "闲鱼" or text.startswith("闲鱼，中国领先的闲置二手交易平台")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="将本机采集页面转换为商品快照 JSONL")
    parser.add_argument("--capture-dir", default="out/captures/inbox")
    parser.add_argument("--output", default="out/product_snapshots.jsonl")
    parser.add_argument("--markdown", default="out/review.md")
    parser.add_argument("--errors", default="out/errors.jsonl")
    parser.add_argument("--raw-dir", default="out/raw")
    args = parser.parse_args(argv)
    try:
        records, failures, details = build_captures(args.capture_dir)
        write_outputs(records, failures, details, output=args.output, markdown=args.markdown, errors=args.errors, raw_dir=args.raw_dir)
    except Exception as exc:
        print(f"构建失败：{exc}", file=sys.stderr)
        return 2
    print(f"构建完成：成功 {len(records)} 条，失败 {len(failures)} 条")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
