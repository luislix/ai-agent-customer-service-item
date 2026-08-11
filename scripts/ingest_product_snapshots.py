"""导入外部爬虫生成的商品 JSONL 快照到 product_rag。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.modules.product_rag.factory import build_service
from src.modules.product_rag.chunker import build_chunks
from src.modules.product_rag.normalizer import snapshot_hash
from src.modules.product_rag.validator import validate_and_normalize


def main() -> int:
    parser = argparse.ArgumentParser(description="导入商品 RAG JSONL 快照")
    parser.add_argument("path", nargs="?", help="JSONL 快照文件路径")
    parser.add_argument("--errors", help="错误报告输出路径（JSONL）")
    parser.add_argument("--validate-only", action="store_true", help="只校验并统计，不连接数据库或调用 Embedding")
    parser.add_argument("--preview", help="校验模式下输出切片预览 JSONL")
    parser.add_argument("--reindex", action="store_true", help="强制重建相同快照的向量")
    args = parser.parse_args()
    if not args.path:
        parser.print_help()
        return 0
    if args.validate_only:
        return _validate_only(args.path, args.errors, args.preview)
    try:
        report = build_service(force_model_reset=args.reindex).import_file(args.path, force_reindex=args.reindex)
    except Exception as exc:  # noqa: BLE001
        print(f"导入失败：{exc}", file=sys.stderr)
        return 2
    if args.errors:
        with open(args.errors, "w", encoding="utf-8") as f:
            for error in report.errors:
                f.write(json.dumps(error.__dict__, ensure_ascii=False) + "\n")
    print(json.dumps({"source": report.source, "accepted": report.accepted, "skipped": report.skipped, "failed": report.failed}, ensure_ascii=False))
    return 1 if report.failed else 0


def _validate_only(path: str, errors_path: str | None, preview_path: str | None) -> int:
    accepted = failed = 0
    errors = []
    previews = []
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        raw = None
        try:
            raw = json.loads(line)
            normalized = validate_and_normalize(raw)
            digest = snapshot_hash(normalized)
            snapshot_id = f"{normalized['item_id']}:{digest[:16]}"
            chunks = build_chunks(normalized, snapshot_id, digest)
            previews.extend({"item_id": chunk.item_id, "chunk_id": chunk.chunk_id, "kind": chunk.kind, "content": chunk.content, "is_dynamic": chunk.is_dynamic, "valid_until": chunk.valid_until.isoformat() if chunk.valid_until else None} for chunk in chunks)
            accepted += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            errors.append({"line_number": line_number, "item_id": raw.get("item_id", "") if isinstance(raw, dict) else "", "error": str(exc)})
    if errors_path:
        Path(errors_path).write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in errors) + ("\n" if errors else ""), encoding="utf-8")
    if preview_path:
        Path(preview_path).write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in previews) + ("\n" if previews else ""), encoding="utf-8")
    print(json.dumps({"source": path, "accepted": accepted, "failed": failed, "chunks": len(previews), "mode": "validate-only"}, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
