"""product_rag 对外稳定契约。具体数据库和 Embedding 实现不得泄漏到调用方。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class RetrievedChunk:
    item_id: str
    chunk_id: str
    kind: str
    content: str
    score: float
    source_url: str = ""
    snapshot_id: str = ""
    updated_at: datetime | None = None
    is_dynamic: bool = False
    valid_until: datetime | None = None


@dataclass(frozen=True)
class KnowledgeChunk:
    item_id: str
    snapshot_id: str
    chunk_id: str
    kind: str
    content: str
    is_dynamic: bool
    valid_until: datetime | None
    source_url: str
    updated_at: datetime
    embedding: tuple[float, ...] = ()


@dataclass(frozen=True)
class ImportErrorRecord:
    line_number: int
    item_id: str
    message: str


@dataclass
class ImportReport:
    source: str = ""
    accepted: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[ImportErrorRecord] = field(default_factory=list)


class ProductKnowledgeRetriever(Protocol):
    def retrieve(self, item_id: str, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        ...


class EmbeddingProvider(Protocol):
    model: str

    def embed(self, texts: list[str]) -> list[list[float]]:
        ...


class KnowledgeChunkRepository(Protocol):
    def has_snapshot(self, item_id: str, snapshot_id: str) -> bool:
        ...

    def replace_snapshot(self, item_id: str, snapshot_id: str, chunks: list[KnowledgeChunk], force: bool = False) -> bool:
        """写入快照；返回 False 表示相同快照已存在。"""
        ...

    def retrieve(self, item_id: str, query_embedding: list[float], top_k: int, min_score: float) -> list[RetrievedChunk]:
        ...


class SnapshotRepository(Protocol):
    def current_hash(self, item_id: str) -> str | None:
        ...

    def save_snapshot(self, item_id: str, snapshot_id: str, snapshot_hash: str, payload: dict[str, Any], updated_at: datetime, source_url: str) -> None:
        ...


class ProductRagImporter(Protocol):
    def import_file(self, path: str | Path) -> ImportReport:
        ...
