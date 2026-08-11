"""商品 RAG 导入与检索编排。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .chunker import build_chunks
from .contracts import EmbeddingProvider, ImportErrorRecord, ImportReport, KnowledgeChunkRepository, ProductKnowledgeRetriever, RetrievedChunk
from .normalizer import snapshot_hash
from .validator import validate_and_normalize


class ProductRagService(ProductKnowledgeRetriever):
    def __init__(self, repository: KnowledgeChunkRepository, embedding: EmbeddingProvider, top_k: int = 5, min_score: float = 0.50):
        self.repository, self.embedding, self.top_k, self.min_score = repository, embedding, top_k, min_score

    def retrieve(self, item_id: str, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        if not item_id or not query.strip(): return []
        vector = self.embedding.embed([query])[0]
        return self.repository.retrieve(item_id, vector, top_k or self.top_k, self.min_score)

    def import_file(self, path: str | Path, force_reindex: bool = False) -> ImportReport:
        report = ImportReport(source=str(path))
        with Path(path).open("r", encoding="utf-8") as source:
            for line_number, line in enumerate(source, 1):
                if not line.strip():
                    continue
                raw: Any = None
                try:
                    raw = json.loads(line)
                except Exception as exc:  # noqa: BLE001
                    report.failed += 1
                    report.errors.append(ImportErrorRecord(line_number, "", str(exc)))
                    continue
                item_report = self.import_records([raw], force_reindex=force_reindex, source=str(path))
                report.accepted += item_report.accepted
                report.skipped += item_report.skipped
                report.failed += item_report.failed
                for error in item_report.errors:
                    report.errors.append(ImportErrorRecord(line_number, error.item_id, error.message))
        return report

    def import_records(self, records: list[dict[str, Any]], force_reindex: bool = False, source: str = "manual") -> ImportReport:
        report = ImportReport(source=source)
        for line_number, raw in enumerate(records, 1):
            try:
                payload = validate_and_normalize(raw)
                digest = snapshot_hash(payload)
                item_id = payload["item_id"]
                snapshot_id = f"{item_id}:{digest[:16]}"
                if self.repository.has_snapshot(item_id, snapshot_id) and not force_reindex:
                    report.skipped += 1
                    continue
                chunks = build_chunks(payload, snapshot_id, digest)
                vectors = self.embedding.embed([c.content for c in chunks]) if chunks else []
                chunks = [c.__class__(**{**c.__dict__, "embedding": tuple(vectors[i])}) for i, c in enumerate(chunks)]
                changed = self.repository.replace_snapshot(item_id, snapshot_id, chunks, force=force_reindex)
                report.accepted += int(changed)
                report.skipped += int(not changed)
            except Exception as exc:  # noqa: BLE001
                report.failed += 1
                item_id = str(raw.get("item_id", "")) if isinstance(raw, dict) else ""
                report.errors.append(ImportErrorRecord(line_number, item_id, str(exc)))
        return report
