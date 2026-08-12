"""推广内容与渠道交付记录。SQLite 实现，任务可恢复且每天幂等。"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class PromotionContent:
    id: int
    content_date: str
    source_pick_id: int
    source_snapshot: dict[str, Any]
    xhs_post: dict[str, Any]
    wechat_article: dict[str, Any]
    asset_dir: str
    status: str
    last_error: str
    created_at: str
    reviewed_at: str | None


@dataclass
class ChannelDelivery:
    id: int
    content_id: int
    channel: str
    status: str
    external_id: str
    asset_path: str
    last_error: str
    attempts: int
    updated_at: str


class PromotionStore:
    def __init__(self, db_path: str):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with closing(self._conn()) as c, c:
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS promotion_contents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content_date TEXT NOT NULL,
                    source_pick_id INTEGER NOT NULL,
                    source_snapshot_json TEXT NOT NULL,
                    xhs_post_json TEXT NOT NULL,
                    wechat_article_json TEXT NOT NULL,
                    asset_dir TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending_review',
                    last_error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                    reviewed_at TEXT,
                    UNIQUE(content_date, source_pick_id)
                )
                """
            )
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS promotion_deliveries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content_id INTEGER NOT NULL,
                    channel TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    external_id TEXT NOT NULL DEFAULT '',
                    asset_path TEXT NOT NULL DEFAULT '',
                    last_error TEXT NOT NULL DEFAULT '',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                    UNIQUE(content_id, channel)
                )
                """
            )

    def create(self, content_date: str, source_pick_id: int, source_snapshot: dict,
               xhs_post: dict, wechat_article: dict) -> tuple[PromotionContent, bool]:
        """创建每日内容及两个渠道交付记录；重复调用返回原记录。"""
        payloads = tuple(json.dumps(value, ensure_ascii=False) for value in
                         (source_snapshot, xhs_post, wechat_article))
        with closing(self._conn()) as c, c:
            cur = c.execute(
                """INSERT OR IGNORE INTO promotion_contents
                   (content_date,source_pick_id,source_snapshot_json,xhs_post_json,wechat_article_json)
                   VALUES (?,?,?,?,?)""",
                (content_date, source_pick_id, *payloads),
            )
            if cur.rowcount:
                content_id = int(cur.lastrowid)
                c.executemany(
                    "INSERT INTO promotion_deliveries(content_id,channel) VALUES (?,?)",
                    [(content_id, "wechat"), (content_id, "xhs")],
                )
                row = c.execute("SELECT * FROM promotion_contents WHERE id=?", (content_id,)).fetchone()
                return self._content(row), True
            row = c.execute(
                "SELECT * FROM promotion_contents WHERE content_date=? AND source_pick_id=?",
                (content_date, source_pick_id),
            ).fetchone()
            return self._content(row), False

    def get(self, content_id: int) -> PromotionContent | None:
        with closing(self._conn()) as c:
            row = c.execute("SELECT * FROM promotion_contents WHERE id=?", (content_id,)).fetchone()
        return self._content(row) if row else None

    def list(self, status: str | None = None) -> list[PromotionContent]:
        sql = "SELECT * FROM promotion_contents"
        args: tuple = ()
        if status:
            sql += " WHERE status=?"
            args = (status,)
        sql += " ORDER BY content_date DESC, id DESC"
        with closing(self._conn()) as c:
            rows = c.execute(sql, args).fetchall()
        return [self._content(row) for row in rows]

    def count(self) -> int:
        with closing(self._conn()) as c:
            return int(c.execute("SELECT COUNT(*) FROM promotion_contents").fetchone()[0])

    def set_assets(self, content_id: int, asset_dir: str) -> None:
        with closing(self._conn()) as c, c:
            c.execute("UPDATE promotion_contents SET asset_dir=? WHERE id=?", (asset_dir, content_id))
            c.execute(
                "UPDATE promotion_deliveries SET asset_path=?, updated_at=datetime('now','localtime') "
                "WHERE content_id=? AND channel='xhs'",
                (asset_dir, content_id),
            )

    def replace_wechat_article(self, content_id: int, article: dict) -> None:
        with closing(self._conn()) as c, c:
            c.execute(
                "UPDATE promotion_contents SET wechat_article_json=? WHERE id=?",
                (json.dumps(article, ensure_ascii=False), content_id),
            )

    def mark_failed(self, content_id: int, reason: str) -> None:
        with closing(self._conn()) as c, c:
            c.execute("UPDATE promotion_contents SET status='failed',last_error=? WHERE id=?", (reason, content_id))

    def reset_failed(self, content_id: int) -> bool:
        """允许渲染失败的内容重新生成；已审核/已交付内容不会被回滚。"""
        with closing(self._conn()) as c, c:
            cur = c.execute(
                "UPDATE promotion_contents SET status='pending_review',last_error='' "
                "WHERE id=? AND status='failed'",
                (content_id,),
            )
            if cur.rowcount:
                c.execute(
                    "UPDATE promotion_deliveries SET status='pending',last_error='',updated_at=datetime('now','localtime') "
                    "WHERE content_id=? AND channel='xhs' AND status='pending'",
                    (content_id,),
                )
            return cur.rowcount > 0

    def approve(self, content_id: int) -> bool:
        with closing(self._conn()) as c, c:
            cur = c.execute(
                "UPDATE promotion_contents SET status='approved',reviewed_at=datetime('now','localtime') "
                "WHERE id=? AND status='pending_review'",
                (content_id,),
            )
            if cur.rowcount:
                c.execute(
                    "UPDATE promotion_deliveries SET status='package_ready',updated_at=datetime('now','localtime') "
                    "WHERE content_id=? AND channel='xhs' AND status='pending'",
                    (content_id,),
                )
            return cur.rowcount > 0

    def reject(self, content_id: int) -> bool:
        with closing(self._conn()) as c, c:
            cur = c.execute(
                "UPDATE promotion_contents SET status='rejected',reviewed_at=datetime('now','localtime') "
                "WHERE id=? AND status='pending_review'",
                (content_id,),
            )
            return cur.rowcount > 0

    def delivery(self, content_id: int, channel: str) -> ChannelDelivery | None:
        with closing(self._conn()) as c:
            row = c.execute(
                "SELECT * FROM promotion_deliveries WHERE content_id=? AND channel=?",
                (content_id, channel),
            ).fetchone()
        return self._delivery(row) if row else None

    def deliveries(self, content_id: int) -> list[ChannelDelivery]:
        with closing(self._conn()) as c:
            rows = c.execute(
                "SELECT * FROM promotion_deliveries WHERE content_id=? ORDER BY channel", (content_id,)
            ).fetchall()
        return [self._delivery(row) for row in rows]

    def record_wechat_draft(self, content_id: int, media_id: str) -> bool:
        with closing(self._conn()) as c, c:
            cur = c.execute(
                """UPDATE promotion_deliveries
                   SET status='draft_created', external_id=?, last_error='', attempts=attempts+1,
                       updated_at=datetime('now','localtime')
                   WHERE content_id=? AND channel='wechat' AND status IN ('pending','failed')""",
                (media_id, content_id),
            )
            return cur.rowcount > 0

    def record_wechat_failure(self, content_id: int, reason: str) -> None:
        with closing(self._conn()) as c, c:
            c.execute(
                """UPDATE promotion_deliveries
                   SET status='failed',last_error=?,attempts=attempts+1,updated_at=datetime('now','localtime')
                   WHERE content_id=? AND channel='wechat'""",
                (reason, content_id),
            )

    def mark_xhs_published(self, content_id: int) -> bool:
        with closing(self._conn()) as c, c:
            cur = c.execute(
                """UPDATE promotion_deliveries SET status='published',updated_at=datetime('now','localtime')
                   WHERE content_id=? AND channel='xhs' AND status IN ('package_ready','awaiting_manual_publish')""",
                (content_id,),
            )
            return cur.rowcount > 0

    def mark_xhs_awaiting_publish(self, content_id: int) -> bool:
        """浏览器完成填充后进入人工点击发布状态。"""
        with closing(self._conn()) as c, c:
            cur = c.execute(
                """UPDATE promotion_deliveries
                   SET status='awaiting_manual_publish',last_error='',updated_at=datetime('now','localtime')
                   WHERE content_id=? AND channel='xhs' AND status IN ('package_ready','failed')""",
                (content_id,),
            )
            return cur.rowcount > 0

    def record_xhs_failure(self, content_id: int, reason: str) -> None:
        with closing(self._conn()) as c, c:
            c.execute(
                """UPDATE promotion_deliveries
                   SET status='failed',last_error=?,attempts=attempts+1,updated_at=datetime('now','localtime')
                   WHERE content_id=? AND channel='xhs'""",
                (reason, content_id),
            )

    @staticmethod
    def _content(row: sqlite3.Row) -> PromotionContent:
        return PromotionContent(
            id=row["id"], content_date=row["content_date"], source_pick_id=row["source_pick_id"],
            source_snapshot=json.loads(row["source_snapshot_json"]), xhs_post=json.loads(row["xhs_post_json"]),
            wechat_article=json.loads(row["wechat_article_json"]), asset_dir=row["asset_dir"],
            status=row["status"], last_error=row["last_error"], created_at=row["created_at"],
            reviewed_at=row["reviewed_at"],
        )

    @staticmethod
    def _delivery(row: sqlite3.Row) -> ChannelDelivery:
        return ChannelDelivery(
            id=row["id"], content_id=row["content_id"], channel=row["channel"], status=row["status"],
            external_id=row["external_id"], asset_path=row["asset_path"], last_error=row["last_error"],
            attempts=row["attempts"], updated_at=row["updated_at"],
        )
