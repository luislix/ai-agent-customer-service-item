from __future__ import annotations

import json
from pathlib import Path

from scripts.merge_keyword_snapshot_runs import merge_keyword_runs


def _record(item_id: str, *, description: str | None = None, source: str | None = None) -> dict:
    return {
        "item_id": item_id,
        "title": f"商品 {item_id}",
        "description": description,
        "source_url": source or f"https://www.goofish.com/item?id={item_id}",
        "updated_at": "2026-08-11T01:00:00Z",
    }


def test_merge_deduplicates_and_prefers_more_complete_record(tmp_path: Path) -> None:
    runs = tmp_path / "keyword-runs"
    first = runs / "task-a"
    second = runs / "task-b"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    (first / "task.json").write_text(json.dumps({"keyword": "手机支架"}), encoding="utf-8")
    (second / "task.json").write_text(json.dumps({"keyword": "项链"}), encoding="utf-8")
    (first / "product_snapshots.jsonl").write_text(
        json.dumps(_record("A1"), ensure_ascii=False) + "\n" + json.dumps(_record("B2")) + "\n",
        encoding="utf-8",
    )
    (second / "product_snapshots.jsonl").write_text(
        json.dumps(_record("A1", description="有人工补充的描述"), ensure_ascii=False) + "\n" + "{bad}\n",
        encoding="utf-8",
    )

    output = tmp_path / "dataset.jsonl"
    report = tmp_path / "merge-report.json"
    review = tmp_path / "review.md"
    result = merge_keyword_runs(runs, output=output, report=report, review=review)

    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert [row["item_id"] for row in rows] == ["A1", "B2"]
    assert rows[0]["description"] == "有人工补充的描述"
    assert result["unique_records"] == 2
    assert result["duplicate_records"] == 1
    assert result["invalid_records"] == 1
    assert result["by_keyword"] == {"手机支架": 2, "项链": 1}
    assert json.loads(report.read_text(encoding="utf-8"))["duplicate_records"] == 1
    assert "商品 A1" in review.read_text(encoding="utf-8")


def test_merge_ignores_output_files_and_reports_missing_task_metadata(tmp_path: Path) -> None:
    runs = tmp_path / "keyword-runs"
    run = runs / "task-no-metadata"
    run.mkdir(parents=True)
    (run / "product_snapshots.jsonl").write_text(json.dumps(_record("A1")) + "\n", encoding="utf-8")

    output = tmp_path / "dataset.jsonl"
    result = merge_keyword_runs(runs, output=output, report=tmp_path / "report.json", review=tmp_path / "review.md")

    assert result["unique_records"] == 1
    assert result["by_keyword"] == {"unknown": 1}
    assert "task-no-metadata" in result["missing_metadata_tasks"]
