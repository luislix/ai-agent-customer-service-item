"""合并终端关键词采集任务的商品快照，供人工审核使用。

该脚本只读取各任务目录中的 JSONL，不导入 RAG、不调用 Embedding，也不修改原始任务。
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

_EXPECTED_FIELDS = (
    "title", "description", "category", "condition", "specifications", "specs",
    "included_items", "inventory", "pricing", "price", "shipping", "after_sale", "faq",
    "source_url", "updated_at",
)


def _non_empty(value: Any) -> bool:
    return value is not None and value != "" and value != {} and value != []


def _completeness(row: dict[str, Any]) -> int:
    return sum(1 for field in _EXPECTED_FIELDS if _non_empty(row.get(field)))


def _updated_at(row: dict[str, Any]) -> datetime:
    value = row.get("updated_at")
    if not isinstance(value, str):
        return datetime.min
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min


def _valid_record(row: Any) -> bool:
    return (
        isinstance(row, dict)
        and isinstance(row.get("item_id"), str)
        and bool(row["item_id"].strip())
        and isinstance(row.get("title"), str)
        and bool(row["title"].strip())
        and isinstance(row.get("source_url"), str)
        and row["source_url"].startswith(("http://", "https://"))
        and isinstance(row.get("updated_at"), str)
    )


def _task_keyword(task_dir: Path) -> str:
    metadata = task_dir / "task.json"
    try:
        payload = json.loads(metadata.read_text(encoding="utf-8"))
        keyword = payload.get("keyword")
        if isinstance(keyword, str) and keyword.strip():
            return keyword.strip()
    except (OSError, json.JSONDecodeError):
        pass
    return "unknown"


def _display_price(pricing: Any) -> str:
    if not isinstance(pricing, dict):
        return "未知"
    if pricing.get("sale_price") is not None:
        return str(pricing["sale_price"])
    if pricing.get("min_price") is not None and pricing.get("max_price") is not None:
        return f"{pricing['min_price']} - {pricing['max_price']}"
    return "未知"


def _review_markdown(rows: list[dict[str, Any]], report: dict[str, Any]) -> str:
    lines = [
        "# 关键词采集商品数据集审阅报告",
        "",
        f"去重后商品：{report['unique_records']} 条；重复：{report['duplicate_records']} 条；无效：{report['invalid_records']} 条。",
        "",
    ]
    for row in rows:
        pricing = row.get("pricing") or row.get("price") or {}
        specs = row.get("specifications") or row.get("specs")
        lines.extend([
            f"## {row['title']}",
            "",
            f"- 商品 ID：`{row['item_id']}`",
            f"- 来源：{row['source_url']}",
            f"- 类目：{row.get('category') or '未提供'}",
            f"- 成色：{row.get('condition') or '未提供'}",
            f"- 价格：{_display_price(pricing)}",
            f"- 规格：{json.dumps(specs, ensure_ascii=False) if specs else '未提供'}",
            f"- 配件：{json.dumps(row.get('included_items'), ensure_ascii=False) if row.get('included_items') else '未提供'}",
            f"- FAQ：{len(row.get('faq') or [])} 条",
            f"- 售后：{'已提供' if _non_empty(row.get('after_sale')) else '未提供'}",
            f"- 采集时间：{row['updated_at']}",
            "",
        ])
    return "\n".join(lines) + "\n"


def merge_keyword_runs(
    run_root: str | Path,
    *,
    output: str | Path,
    report: str | Path,
    review: str | Path,
    keyword_overrides: dict[str, str] | None = None,
    max_records: int | None = None,
) -> dict[str, Any]:
    root = Path(run_root)
    candidates = sorted(root.glob("*/product_snapshots.jsonl"))
    selected: dict[str, tuple[dict[str, Any], str, int]] = {}
    duplicate_records = 0
    invalid_records = 0
    input_records = 0
    by_keyword: Counter[str] = Counter()
    missing_metadata_tasks: list[str] = []
    duplicate_sources: list[dict[str, str]] = []

    keyword_overrides = keyword_overrides or {}
    for path in candidates:
        keyword = keyword_overrides.get(path.parent.name, _task_keyword(path.parent))
        valid_in_file = 0
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            input_records += 1
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                invalid_records += 1
                continue
            if not _valid_record(row):
                invalid_records += 1
                continue
            valid_in_file += 1
            item_id = row["item_id"].strip()
            by_keyword[keyword] += 1
            candidate = (row, str(path), _completeness(row))
            previous = selected.get(item_id)
            if previous is None:
                selected[item_id] = candidate
                continue
            duplicate_records += 1
            old_row, old_path, old_score = previous
            if (candidate[2], _updated_at(row), str(path)) > (old_score, _updated_at(old_row), old_path):
                selected[item_id] = candidate
                kept, dropped = str(path), old_path
            else:
                kept, dropped = old_path, str(path)
            duplicate_sources.append({"item_id": item_id, "kept": kept, "dropped": dropped})
        if keyword == "unknown" and valid_in_file:
            missing_metadata_tasks.append(path.parent.name)

    selected_rows = list(selected.values())
    trimmed_item_ids: list[str] = []
    if max_records is not None:
        if max_records < 1:
            raise ValueError("max_records 必须大于 0")
        selected_rows.sort(key=lambda item: (item[2], _updated_at(item[0]), item[0]["item_id"]), reverse=True)
        trimmed_item_ids = [row[0]["item_id"] for row in selected_rows[max_records:]]
        selected_rows = selected_rows[:max_records]
    rows = sorted((item[0] for item in selected_rows), key=lambda row: row["item_id"])
    selected_by_keyword: Counter[str] = Counter()
    # Resolve keyword counts from the selected source paths before serializing.
    source_by_item = {item_id: candidate[1] for item_id, candidate in selected.items() if item_id not in trimmed_item_ids}
    for item_id, source_path in source_by_item.items():
        selected_by_keyword[keyword_overrides.get(Path(source_path).parent.name, _task_keyword(Path(source_path).parent))] += 1
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")
    result: dict[str, Any] = {
        "run_root": str(root),
        "input_files": len(candidates),
        "input_records": input_records,
        "unique_records": len(rows),
        "duplicate_records": duplicate_records,
        "invalid_records": invalid_records,
        "by_keyword": dict(sorted(by_keyword.items())),
        "missing_metadata_tasks": sorted(set(missing_metadata_tasks)),
        "max_records": max_records,
        "trimmed_records": len(trimmed_item_ids),
        "trimmed_item_ids": sorted(trimmed_item_ids),
        "selected_by_keyword": dict(sorted(selected_by_keyword.items())),
        "duplicates": duplicate_sources,
    }
    report_path = Path(report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    Path(review).write_text(_review_markdown(rows, result), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="合并关键词采集任务的商品快照")
    parser.add_argument("--run-root", default="xianyu_product_crawler/out/keyword-runs")
    parser.add_argument("--output", default="xianyu_product_crawler/out/keyword-dataset.jsonl")
    parser.add_argument("--report", default="xianyu_product_crawler/out/keyword-dataset.merge-report.json")
    parser.add_argument("--review", default="xianyu_product_crawler/out/keyword-dataset.review.md")
    parser.add_argument("--max-records", type=int, help="最多保留多少个唯一商品；超出部分按资料完整度和更新时间淘汰")
    parser.add_argument(
        "--legacy-keyword",
        action="append",
        default=[],
        metavar="TASK_ID=KEYWORD",
        help="为没有 task.json 的历史任务补充关键词，可重复传入",
    )
    args = parser.parse_args()
    overrides = {}
    for value in args.legacy_keyword:
        if "=" not in value:
            parser.error("--legacy-keyword 必须是 TASK_ID=KEYWORD")
        task_id, keyword = value.split("=", 1)
        if not task_id or not keyword.strip():
            parser.error("--legacy-keyword 的任务 ID 和关键词不能为空")
        overrides[task_id] = keyword.strip()
    result = merge_keyword_runs(
        args.run_root,
        output=args.output,
        report=args.report,
        review=args.review,
        keyword_overrides=overrides,
        max_records=args.max_records,
    )
    print(json.dumps({key: result[key] for key in ("input_files", "input_records", "unique_records", "duplicate_records", "invalid_records")}, ensure_ascii=False))
    return 1 if result["invalid_records"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
