"""无外部依赖的测试/开发实现；生产环境替换为 pgvector repository。"""
from __future__ import annotations

from datetime import datetime, timezone
from math import sqrt

from .contracts import KnowledgeChunk, RetrievedChunk


class InMemoryKnowledgeStore:
    def __init__(self, chunks: list[KnowledgeChunk] | None = None):
        self.chunks = list(chunks or [])

    def replace_snapshot(self, item_id: str, snapshot_id: str, chunks: list[KnowledgeChunk], force: bool = False) -> bool:
        if self.has_snapshot(item_id, snapshot_id) and not force:
            return False
        self.chunks = [c for c in self.chunks if c.item_id != item_id]
        self.chunks.extend(chunks)
        return True

    def has_snapshot(self, item_id: str, snapshot_id: str) -> bool:
        return any(c.item_id == item_id and c.snapshot_id == snapshot_id for c in self.chunks)

    def retrieve(self, item_id: str, query_embedding: list[float], top_k: int, min_score: float) -> list[RetrievedChunk]:
        now = datetime.now(timezone.utc)
        candidates = [c for c in self.chunks if c.item_id == item_id and (c.valid_until is None or c.valid_until > now)]
        scored = []
        for c in candidates:
            score = _cosine(query_embedding, list(c.embedding)) if c.embedding else 0.0
            if score >= min_score:
                scored.append(RetrievedChunk(c.item_id, c.chunk_id, c.kind, c.content, score, c.source_url, c.snapshot_id, c.updated_at, c.is_dynamic, c.valid_until))
        return sorted(scored, key=lambda x: (x.kind != "faq", -x.score))[:top_k]


def _cosine(a, b):
    if not a or not b or len(a) != len(b): return 0.0
    denom = sqrt(sum(x*x for x in a) * sum(x*x for x in b))
    return sum(x*y for x, y in zip(a, b)) / denom if denom else 0.0
