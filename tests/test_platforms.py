"""统一渠道框架测试：心理价、渠道利润测算、推荐最优渠道、亏本剔除、国内/跨境封装（离线）。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.modules.sourcing.agent import SourcingAgent  # noqa: E402
from src.modules.sourcing.onebound_client import OneboundClient  # noqa: E402
from src.modules.sourcing.platforms import (  # noqa: E402
    PROFILES, estimate_freight, psych_local, quote, resolve_profiles, select_platforms,
)
from src.modules.sourcing.types import SourcedItem  # noqa: E402


class TestPsychLocal(unittest.TestCase):
    def test_cross_border_ends_99(self):
        self.assertEqual(psych_local(15.4, True), 15.99)
        self.assertEqual(psych_local(15.0, True), 15.99)

    def test_domestic_ends_9(self):
        # 国内复用 .9 结尾心理价
        self.assertEqual(psych_local(48, False), 49)


class TestQuote(unittest.TestCase):
    def test_cross_border_profit_positive(self):
        item = SourcedItem(item_id="x", title="t", cost_price=30, sales=2000)
        q = quote(item, PROFILES["tiktok_us"])
        self.assertTrue(q.cross_border)
        self.assertEqual(q.currency, "US$")
        self.assertGreater(q.profit, 0)
        self.assertAlmostEqual(q.resale_rmb, q.resale_local * PROFILES["tiktok_us"].fx_to_rmb, places=2)

    def test_domestic_profit(self):
        item = SourcedItem(item_id="x", title="t", cost_price=30, sales=2000)
        q = quote(item, PROFILES["xianyu"])
        self.assertFalse(q.cross_border)
        self.assertEqual(q.resale_local, q.resale_rmb)   # 国内汇率=1
        self.assertGreater(q.profit, 0)


class TestFreight(unittest.TestCase):
    def test_freight_scales_with_size(self):
        p = PROFILES["tiktok_us"]
        small = estimate_freight(30, p)
        mid = estimate_freight(100, p)
        big = estimate_freight(200, p)
        self.assertEqual(small, p.fulfillment_rmb)
        self.assertEqual(mid, p.fulfillment_rmb * 2.5)
        self.assertEqual(big, p.fulfillment_rmb * 5.0)
        self.assertGreater(big, mid)
        self.assertGreater(mid, small)


class TestResolve(unittest.TestCase):
    def test_subset_and_fallback(self):
        self.assertEqual([p.key for p in resolve_profiles(["tiktok_us"])], ["tiktok_us"])
        # None/全未知 回退跨境默认
        self.assertEqual([p.key for p in resolve_profiles(None)], ["tiktok_us", "aliexpress"])
        self.assertEqual([p.key for p in resolve_profiles(["nope"])], ["tiktok_us", "aliexpress"])
        # 国内渠道也能解析
        self.assertEqual([p.key for p in resolve_profiles(["xianyu", "pdd"])], ["xianyu", "pdd"])


class TestSelectPlatforms(unittest.TestCase):
    def test_picks_best_and_sorted(self):
        items = [
            SourcedItem(item_id="a", title="爆款", cost_price=30, sales=8000),
            SourcedItem(item_id="b", title="冷门", cost_price=80, sales=20),
        ]
        picks = select_platforms(items, markets=["tiktok_us", "aliexpress"])
        self.assertTrue(picks)
        self.assertGreaterEqual(picks[0].score, picks[-1].score)
        self.assertEqual(picks[0].best.platform, "TikTok Shop 美国")   # 佣金更低利润更高
        self.assertEqual(len(picks[0].quotes), 2)
        self.assertIn("推荐", picks[0].reason)

    def test_drops_loss_making(self):
        # 进价 1 元，跨境物流 20-25 元吃光利润 -> 剔除
        items = [SourcedItem(item_id="z", title="亏本", cost_price=1, sales=500)]
        self.assertEqual(select_platforms(items, markets=["tiktok_us", "aliexpress"]), [])

    def test_skips_zero_cost(self):
        items = [SourcedItem(item_id="z", title="无价", cost_price=0, sales=100)]
        self.assertEqual(select_platforms(items), [])


class TestAgentFacades(unittest.TestCase):
    def test_find_overseas_offline(self):
        picks = SourcingAgent(OneboundClient(api_key="")).find_overseas(
            "保温杯", min_sales=100, top_k=3,
        )
        self.assertTrue(picks)
        self.assertTrue(all(p.best.profit > 0 for p in picks))
        self.assertTrue(all(p.best.cross_border for p in picks))

    def test_find_domestic_offline(self):
        picks = SourcingAgent(OneboundClient(api_key="")).find_domestic(
            "保温杯", min_sales=100, top_k=3,
        )
        self.assertTrue(picks)
        self.assertTrue(all(p.best.platform in ("闲鱼", "拼多多", "抖音小店") for p in picks))
        self.assertTrue(all(not p.best.cross_border for p in picks))


if __name__ == "__main__":
    unittest.main()
