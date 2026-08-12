"""SQLite 持久化调度锁，防止守护进程重启后重复执行当天任务。"""
from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path


class ScheduleRunStore:
    def __init__(self, db_path: str):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        with closing(self._conn()) as c, c:
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS scheduled_runs (
                    task TEXT NOT NULL,
                    run_date TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'running',
                    updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                    PRIMARY KEY (task, run_date)
                )
                """
            )

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def start(self, task: str, run_date: str) -> bool:
        """原子占用当天任务；已有 running/completed 记录时返回 False。"""
        with closing(self._conn()) as c, c:
            cur = c.execute(
                "INSERT OR IGNORE INTO scheduled_runs(task,run_date,status) VALUES (?,?, 'running')",
                (task, run_date),
            )
            return cur.rowcount > 0

    def complete(self, task: str, run_date: str) -> None:
        with closing(self._conn()) as c, c:
            c.execute(
                "UPDATE scheduled_runs SET status='completed', updated_at=datetime('now','localtime') "
                "WHERE task=? AND run_date=?",
                (task, run_date),
            )

    def fail(self, task: str, run_date: str) -> None:
        with closing(self._conn()) as c, c:
            c.execute(
                "UPDATE scheduled_runs SET status='failed', updated_at=datetime('now','localtime') "
                "WHERE task=? AND run_date=?",
                (task, run_date),
            )
