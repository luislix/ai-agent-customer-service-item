"""每日选品清单存储：定时选品的结果落库，人工后台逐条勾选（approve/reject）。

用 sqlite、零外部依赖，与 work_order 同风格。生产可换 PostgreSQL/MySQL。
"""
from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from .platforms import PlatformPick


@dataclass
class DailyPick:
    id: int
    run_date: str        # 选品日期 YYYY-MM-DD
    keyword: str
    group: str           # overseas / domestic
    item_id: str
    title: str
    cost_price: float
    platform: str        # 推荐渠道名
    currency: str
    resale_local: float  # 推荐渠道售价（本币）
    profit: float        # 净利（RMB）
    margin: float
    score: float
    sales: int
    detail_url: str
    status: str          # pending / approved / rejected
    created_at: str


class SourcingPickStore:
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
                CREATE TABLE IF NOT EXISTS daily_picks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_date TEXT NOT NULL,
                    keyword TEXT NOT NULL,
                    "group" TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    cost_price REAL NOT NULL,
                    platform TEXT NOT NULL,
                    currency TEXT NOT NULL DEFAULT '¥',
                    resale_local REAL NOT NULL,
                    profit REAL NOT NULL,
                    margin REAL NOT NULL,
                    score REAL NOT NULL,
                    sales INTEGER NOT NULL DEFAULT 0,
                    detail_url TEXT DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
                )
                """
            )

    def save(self, run_date: str, keyword: str, group: str, pick: PlatformPick) -> int:
        """把一条选品决策落库。同 run_date+item_id+group 视为重复，跳过返回 0。"""
        b = pick.best
        with closing(self._conn()) as c, c:
            dup = c.execute(
                'SELECT 1 FROM daily_picks WHERE run_date=? AND item_id=? AND "group"=?',
                (run_date, pick.item.item_id, group),
            ).fetchone()
            if dup:
                return 0
            cur = c.execute(
                """INSERT INTO daily_picks
                   (run_date,keyword,"group",item_id,title,cost_price,platform,currency,
                    resale_local,profit,margin,score,sales,detail_url)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (run_date, keyword, group, pick.item.item_id, pick.item.title,
                 pick.item.cost_price, b.platform, b.currency, b.resale_local,
                 b.profit, b.margin, pick.score, pick.item.sales, pick.item.detail_url),
            )
            return int(cur.lastrowid)

    def list_pending(self, run_date: str | None = None, group: str | None = None) -> list[DailyPick]:
        sql = "SELECT * FROM daily_picks WHERE status='pending'"
        args: list = []
        if run_date:
            sql += " AND run_date=?"
            args.append(run_date)
        if group:
            sql += ' AND "group"=?'
            args.append(group)
        sql += " ORDER BY score DESC"
        with closing(self._conn()) as c:
            rows = c.execute(sql, tuple(args)).fetchall()
        return [self._row(r) for r in rows]

    def list_picks(self, status: str | None = None, group: str | None = None,
                   run_date: str | None = None) -> list[DailyPick]:
        """通用查询（控制台用）：按状态/分组/日期筛选，按评分降序。"""
        sql = "SELECT * FROM daily_picks WHERE 1=1"
        args: list = []
        if status:
            sql += " AND status=?"
            args.append(status)
        if group:
            sql += ' AND "group"=?'
            args.append(group)
        if run_date:
            sql += " AND run_date=?"
            args.append(run_date)
        sql += " ORDER BY score DESC"
        with closing(self._conn()) as c:
            rows = c.execute(sql, tuple(args)).fetchall()
        return [self._row(r) for r in rows]

    def get_pick(self, pick_id: int) -> DailyPick | None:
        """供组合层读取单条选品；知识库模块本身不依赖此接口。"""
        with closing(self._conn()) as c:
            row = c.execute("SELECT * FROM daily_picks WHERE id=?", (pick_id,)).fetchone()
        return self._row(row) if row else None

    def stats(self) -> dict:
        """各状态计数（控制台顶部用）：{pending, approved, rejected}。"""
        with closing(self._conn()) as c:
            rows = c.execute(
                "SELECT status, COUNT(*) AS c FROM daily_picks GROUP BY status"
            ).fetchall()
        out = {"pending": 0, "approved": 0, "rejected": 0}
        for r in rows:
            out[r["status"]] = r["c"]
        return out

    def approve(self, pick_id: int) -> bool:
        return self._set_status(pick_id, "approved")

    def reject(self, pick_id: int) -> bool:
        return self._set_status(pick_id, "rejected")

    def _set_status(self, pick_id: int, status: str) -> bool:
        with closing(self._conn()) as c, c:
            cur = c.execute(
                "UPDATE daily_picks SET status=? WHERE id=? AND status='pending'",
                (status, pick_id),
            )
            return cur.rowcount > 0

    def count_pending(self, run_date: str | None = None) -> int:
        return len(self.list_pending(run_date))

    @staticmethod
    def _row(r: sqlite3.Row) -> DailyPick:
        return DailyPick(
            id=r["id"], run_date=r["run_date"], keyword=r["keyword"], group=r["group"],
            item_id=r["item_id"], title=r["title"], cost_price=r["cost_price"],
            platform=r["platform"], currency=r["currency"], resale_local=r["resale_local"],
            profit=r["profit"], margin=r["margin"], score=r["score"], sales=r["sales"],
            detail_url=r["detail_url"], status=r["status"], created_at=r["created_at"],
        )
