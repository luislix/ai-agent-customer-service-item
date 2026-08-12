"""持久化调度锁：进程重启后同一任务日期不重复执行。"""
import tempfile
import unittest
from pathlib import Path

from src.core.schedule_store import ScheduleRunStore


class TestScheduleRunStore(unittest.TestCase):
    def test_completed_run_cannot_be_started_twice_after_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "app.db")
            first = ScheduleRunStore(path)
            self.assertTrue(first.start("promotion", "2026-08-11"))
            first.complete("promotion", "2026-08-11")
            second = ScheduleRunStore(path)
            self.assertFalse(second.start("promotion", "2026-08-11"))


if __name__ == "__main__":
    unittest.main()
