"""每日选品任务 + 清单存储测试：落库、去重、勾选、按评分排序、编排状态感知（离线）。"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.modules.sourcing.agent import SourcingAgent  # noqa: E402
from src.modules.sourcing.daily_job import run_daily_sourcing  # noqa: E402
from src.modules.sourcing.onebound_client import OneboundClient  # noqa: E402
from src.modules.sourcing.store import SourcingPickStore  # noqa: E402

_DATE = "2026-06-29"


def _offline_agent():
    return SourcingAgent(OneboundClient(api_key=""))


class TestDailyJob(unittest.TestCase):
    def setUp(self):
        self.db = str(Path(tempfile.mkdtemp()) / "t.db")
        self.store = SourcingPickStore(self.db)
        self.agent = _offline_agent()

    def test_run_and_persist_sorted(self):
        s = run_daily_sourcing(["保温杯"], self.store, agent=self.agent, run_date=_DATE, top_k=2)
        self.assertEqual(s["run_date"], _DATE)
        self.assertGreater(s["saved"], 0)
        pend = self.store.list_pending(run_date=_DATE)
        self.assertEqual(len(pend), s["saved"])
        scores = [p.score for p in pend]
        self.assertEqual(scores, sorted(scores, reverse=True))   # 按评分降序

    def test_dedup_same_day(self):
        run_daily_sourcing(["保温杯"], self.store, agent=self.agent, run_date=_DATE)
        before = self.store.count_pending()
        run_daily_sourcing(["保温杯"], self.store, agent=self.agent, run_date=_DATE)  # 同日再跑
        self.assertEqual(self.store.count_pending(), before)     # 去重不翻倍

    def test_approve_then_locked(self):
        run_daily_sourcing(["保温杯"], self.store, agent=self.agent, run_date=_DATE, top_k=3)
        pend = self.store.list_pending()
        pid = pend[0].id
        self.assertTrue(self.store.approve(pid))
        self.assertFalse(self.store.approve(pid))                # 已处理不可重复
        self.assertEqual(self.store.count_pending(), len(pend) - 1)


class TestOrchestratorStateAware(unittest.TestCase):
    def _orch(self):
        from src.orchestrator import Orchestrator
        return Orchestrator()

    def test_skips_when_manual(self):
        orch = self._orch()
        orch.modules["sourcing"].sm.force_manual("test_pause")
        store = SourcingPickStore(str(Path(tempfile.mkdtemp()) / "o.db"))
        res = orch.run_sourcing_job(["保温杯"], store=store, agent=_offline_agent(), run_date=_DATE)
        self.assertIsNone(res)                                   # MANUAL 跳过
        self.assertEqual(store.count_pending(), 0)

    def test_runs_when_auto(self):
        orch = self._orch()  # 初始 AUTO
        store = SourcingPickStore(str(Path(tempfile.mkdtemp()) / "o.db"))
        res = orch.run_sourcing_job(["保温杯"], store=store, agent=_offline_agent(), run_date=_DATE)
        self.assertIsNotNone(res)
        self.assertGreater(res["saved"], 0)


if __name__ == "__main__":
    unittest.main()
