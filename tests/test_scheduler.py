"""定时调度判断测试：到点触发、当天去重、跨天重置。"""
import datetime
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.scheduler import should_run  # noqa: E402


class TestShouldRun(unittest.TestCase):
    def test_runs_at_or_after_hour_when_not_run_today(self):
        now = datetime.datetime(2026, 6, 29, 9, 0)
        self.assertTrue(should_run(now, run_hour=9, last_run_date=None))
        self.assertTrue(should_run(now, run_hour=9, last_run_date="2026-06-28"))

    def test_not_before_hour(self):
        now = datetime.datetime(2026, 6, 29, 8, 59)
        self.assertFalse(should_run(now, run_hour=9, last_run_date=None))

    def test_dedup_same_day(self):
        now = datetime.datetime(2026, 6, 29, 10, 0)
        self.assertFalse(should_run(now, run_hour=9, last_run_date="2026-06-29"))

    def test_resets_next_day(self):
        now = datetime.datetime(2026, 6, 30, 9, 1)
        self.assertTrue(should_run(now, run_hour=9, last_run_date="2026-06-29"))


if __name__ == "__main__":
    unittest.main()
