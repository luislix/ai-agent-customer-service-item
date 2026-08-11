"""人工商品知识入库。

该模块只接收已由组合层确认的候选商品，不依赖选品模块或客服模块。草稿与发布
分开，避免选品审核后自动写入 RAG。
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from .validator import validate_and_normalize


class SnapshotImporter(Protocol):
    def import_records(self, records: list[dict[str, Any]]) -> Any:
        ...


@dataclass(frozen=True)
class KnowledgeDraftInput:
    source_pick_id: int
    source_item_id: str
    title: str
    source_url: str
    suggested_price: float
    currency: str


@dataclass(frozen=True)
class KnowledgeDraft:
    id: int
    source_pick_id: int
    source_item_id: str
    title: str
    source_url: str
    suggested_price: float
    currency: str
    status: str
    xianyu_item_id: str
    created_at: str
    published_at: str | None


class ManualKnowledgeIngestionStore:
    """知识库模块拥有的草稿表，和选品表没有数据库耦合。"""

    def __init__(self, db_path: str):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with closing(self._conn()) as conn, conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS product_knowledge_drafts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_pick_id INTEGER NOT NULL UNIQUE,
                    source_item_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    suggested_price REAL NOT NULL,
                    currency TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'draft',
                    xianyu_item_id TEXT NOT NULL DEFAULT '',
                    snapshot_json TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                    published_at TEXT
                )
                """
            )

    def create(self, source: KnowledgeDraftInput) -> KnowledgeDraft:
        with closing(self._conn()) as conn, conn:
            try:
                cur = conn.execute(
                    """INSERT INTO product_knowledge_drafts
                    (source_pick_id, source_item_id, title, source_url, suggested_price, currency)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                    (source.source_pick_id, source.source_item_id, source.title, source.source_url,
                     source.suggested_price, source.currency),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("该选品已创建知识库草稿") from exc
        return self.get(int(cur.lastrowid))

    def get(self, draft_id: int) -> KnowledgeDraft:
        with closing(self._conn()) as conn:
            row = conn.execute("SELECT * FROM product_knowledge_drafts WHERE id=?", (draft_id,)).fetchone()
        if row is None:
            raise ValueError("知识库草稿不存在")
        return self._row(row)

    def list_drafts(self) -> list[KnowledgeDraft]:
        with closing(self._conn()) as conn:
            rows = conn.execute("SELECT * FROM product_knowledge_drafts ORDER BY id DESC").fetchall()
        return [self._row(row) for row in rows]

    def mark_published(self, draft_id: int, xianyu_item_id: str, snapshot: dict[str, Any]) -> None:
        with closing(self._conn()) as conn, conn:
            cur = conn.execute(
                """UPDATE product_knowledge_drafts
                SET status='published', xianyu_item_id=?, snapshot_json=?,
                    published_at=datetime('now','localtime')
                WHERE id=? AND status='draft'""",
                (xianyu_item_id, json.dumps(snapshot, ensure_ascii=False), draft_id),
            )
        if cur.rowcount != 1:
            raise ValueError("知识库草稿已发布或不存在")

    @staticmethod
    def _row(row: sqlite3.Row) -> KnowledgeDraft:
        return KnowledgeDraft(
            id=row["id"], source_pick_id=row["source_pick_id"], source_item_id=row["source_item_id"],
            title=row["title"], source_url=row["source_url"], suggested_price=row["suggested_price"],
            currency=row["currency"], status=row["status"], xianyu_item_id=row["xianyu_item_id"],
            created_at=row["created_at"], published_at=row["published_at"],
        )


class ManualKnowledgeIngestion:
    def __init__(self, store: ManualKnowledgeIngestionStore, importer: SnapshotImporter):
        self.store = store
        self.importer = importer

    def create_draft(self, source: KnowledgeDraftInput) -> KnowledgeDraft:
        return self.store.create(source)

    def publish(self, draft_id: int, xianyu_item_id: str, facts: dict[str, Any]) -> dict[str, Any]:
        if not xianyu_item_id.strip():
            raise ValueError("必须绑定闲鱼商品 ID 后才能入库")
        draft = self.store.get(draft_id)
        if draft.status != "draft":
            raise ValueError("知识库草稿已发布")
        payload = {
            "item_id": xianyu_item_id.strip(),
            "title": draft.title,
            "price": {"sale_price": draft.suggested_price, "currency": draft.currency},
            "source_url": draft.source_url,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            **facts,
        }
        try:
            snapshot = validate_and_normalize(payload)
        except Exception as exc:
            raise ValueError(f"商品资料校验失败：{exc}") from exc
        report = self.importer.import_records([snapshot])
        if getattr(report, "failed", 0):
            raise RuntimeError("商品知识入库失败，草稿保持待发布状态")
        self.store.mark_published(draft.id, snapshot["item_id"], snapshot)
        return snapshot
