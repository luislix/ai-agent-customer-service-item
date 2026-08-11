"""工单队列：降级期间未完成的动作（待发货/待回复/待发帖）落库，人工后台逐条处理。

用 sqlite，零外部依赖，保证脚手架开箱即跑。生产可换 PostgreSQL/MySQL。
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path


@dataclass
class WorkOrder:
    id: int
    module: str          # customer / sourcing / promotion
    action: str          # 如 ship_order / reply_message / publish_post
    payload: dict        # 该动作所需的数据（不丢）
    status: str          # pending / done / cancelled
    reason: str          # 为什么进工单（降级原因）
    created_at: str


class WorkOrderStore:
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
                CREATE TABLE IF NOT EXISTS work_orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    module TEXT NOT NULL,
                    action TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    reason TEXT DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
                )
                """
            )

    def create(self, module: str, action: str, payload: dict, reason: str = "") -> int:
        with closing(self._conn()) as c, c:
            cur = c.execute(
                "INSERT INTO work_orders(module, action, payload, reason) VALUES (?,?,?,?)",
                (module, action, json.dumps(payload, ensure_ascii=False), reason),
            )
            return int(cur.lastrowid)

    def list_pending(self, module: str | None = None) -> list[WorkOrder]:
        sql = "SELECT * FROM work_orders WHERE status='pending'"
        args: tuple = ()
        if module:
            sql += " AND module=?"
            args = (module,)
        sql += " ORDER BY id"
        with closing(self._conn()) as c:
            rows = c.execute(sql, args).fetchall()
        return [self._row(r) for r in rows]

    def complete(self, order_id: int) -> bool:
        with closing(self._conn()) as c, c:
            cur = c.execute(
                "UPDATE work_orders SET status='done' WHERE id=? AND status='pending'",
                (order_id,),
            )
            return cur.rowcount > 0

    def count_pending(self, module: str | None = None) -> int:
        return len(self.list_pending(module))

    @staticmethod
    def _row(r: sqlite3.Row) -> WorkOrder:
        return WorkOrder(
            id=r["id"],
            module=r["module"],
            action=r["action"],
            payload=json.loads(r["payload"]),
            status=r["status"],
            reason=r["reason"],
            created_at=r["created_at"],
        )
