from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .models import CrawlFailure, ItemDetail
from .redact import redact


def write_outputs(records: list[dict], failures: Iterable[CrawlFailure], raw_details: Iterable[ItemDetail], *, output: str | Path, markdown: str | Path, errors: str | Path, raw_dir: str | Path | None = None) -> None:
    failures = list(failures)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in records), encoding="utf-8")
    markdown_path = Path(markdown)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# 商品快照审阅报告", "", f"成功 {len(records)} 条，失败 {len(failures)} 条。", ""]
    for row in records:
        pricing = row.get("pricing") or row.get("price") or {}
        specs = row.get("specifications") or row.get("specs")
        lines.extend([
            f"## {row['title']}", "", f"- 商品 ID：`{row['item_id']}`", f"- 来源：{row['source_url']}",
            f"- 类目：{row.get('category') or '未提供'}", f"- 价格：{pricing.get('sale_price', '未知')}",
            f"- 规格：{json.dumps(specs, ensure_ascii=False) if specs else '未提供'}",
            f"- 配件：{json.dumps(row.get('included_items'), ensure_ascii=False) if row.get('included_items') else '未提供'}",
            f"- 采集时间：{row['updated_at']}", "",
        ])
    if failures:
        lines.extend(["## 失败记录", ""])
        lines.extend(f"- `{failure.item_id or '-'}`（{failure.keyword}/{failure.stage}）：{failure.error}" for failure in failures)
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    error_path = Path(errors)
    error_path.parent.mkdir(parents=True, exist_ok=True)
    error_path.write_text("".join(json.dumps(failure.__dict__, ensure_ascii=False) + "\n" for failure in failures), encoding="utf-8")
    if raw_dir is not None:
        raw_path = Path(raw_dir)
        raw_path.mkdir(parents=True, exist_ok=True)
        for detail in raw_details:
            safe = redact({"item_id": detail.item_id, "source_url": detail.source_url, "payload": detail.payload})
            (raw_path / f"{detail.item_id}.json").write_text(json.dumps(safe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
