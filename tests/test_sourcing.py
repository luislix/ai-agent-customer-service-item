"""选品模块离线测试：样例搜索、定价心理价、打分排序、过滤、桥接推广（不需 key/网络）。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.modules.promotion.types import Product  # noqa: E402
from src.modules.sourcing.agent import (  # noqa: E402
    SourcingAgent, to_promo_product,
)
from src.modules.sourcing.onebound_client import (  # noqa: E402
    OneboundClient, _decode, parse_quota,
)
from src.modules.sourcing.selector import (  # noqa: E402
    psych_price, score_item, select, suggest_resale,
)
from src.modules.sourcing.types import SourcedItem, SourcingQuery  # noqa: E402


class TestPricing(unittest.TestCase):
    def test_psych_price_ends_in_9(self):
        self.assertEqual(psych_price(35.1), 39)
        self.assertEqual(psych_price(128), 129)
        self.assertEqual(psych_price(6.2), 9.9)
        self.assertEqual(psych_price(120), 119)   # 整十向上不补成 121

    def test_suggest_resale_respects_min_profit(self):
        # 进货 5 元，60% 加成只有 3 元利润 < 保底 10 -> 至少 15，再取心理价
        r = suggest_resale(5.0, markup=0.6, min_profit=10.0)
        self.assertGreaterEqual(r - 5.0, 10.0)

    def test_score_profit_and_margin(self):
        item = SourcedItem(item_id="x", title="t", cost_price=20, sales=1000)
        score, profit, margin = score_item(item, resale=49)
        self.assertAlmostEqual(profit, 29.0)
        self.assertAlmostEqual(margin, round(29 / 49, 3))
        self.assertGreater(score, 0)


class TestOfflineClient(unittest.TestCase):
    def test_offline_when_no_key(self):
        client = OneboundClient(api_key="", secret="")
        self.assertFalse(client.available)
        items = client.search(SourcingQuery(keyword="保温杯"))
        self.assertTrue(items)
        self.assertTrue(all("保温杯" in it.title for it in items))

    def test_offline_respects_price_filter(self):
        client = OneboundClient(api_key="", secret="")
        items = client.search(SourcingQuery(keyword="杯", max_price=20))
        self.assertTrue(all(it.cost_price <= 20 for it in items))

    def test_offline_respects_min_sales(self):
        client = OneboundClient(api_key="", secret="")
        items = client.search(SourcingQuery(keyword="杯", min_sales=1000))
        self.assertTrue(all(it.sales >= 1000 for it in items))


class TestDecodeAndQuota(unittest.TestCase):
    def test_decode_utf8(self):
        self.assertEqual(_decode("保温杯".encode("utf-8")), "保温杯")

    def test_decode_falls_back_to_gbk(self):
        # 模拟 Onebound 谎称 utf-8 实则 GBK 的报错响应：utf-8 解会抛异常，应回退 GBK
        raw = "密钥错误,无权限访问".encode("gbk")
        with self.assertRaises(UnicodeDecodeError):
            raw.decode("utf-8")
        self.assertEqual(_decode(raw), "密钥错误,无权限访问")

    def test_parse_quota_extracts_fields(self):
        data = {"api_info": "today:0 max:10 all[2=0+0+2];expires:2026-06-27"}
        q = parse_quota(data)
        self.assertEqual(q["today"], "0")
        self.assertEqual(q["max"], "10")
        self.assertEqual(q["expires"], "2026-06-27")

    def test_parse_quota_none_when_absent(self):
        self.assertIsNone(parse_quota({}))
        self.assertIsNone(parse_quota({"api_info": ""}))


class TestSelectRanking(unittest.TestCase):
    def test_select_sorted_desc_and_topk(self):
        items = [
            SourcedItem(item_id="a", title="低销量", cost_price=50, sales=10),
            SourcedItem(item_id="b", title="爆款", cost_price=20, sales=8000),
            SourcedItem(item_id="c", title="中等", cost_price=30, sales=800),
        ]
        picks = select(items, top_k=2)
        self.assertEqual(len(picks), 2)
        self.assertGreaterEqual(picks[0].score, picks[1].score)
        self.assertEqual(picks[0].item.item_id, "b")   # 爆款评分最高

    def test_select_skips_zero_cost(self):
        items = [SourcedItem(item_id="z", title="无价", cost_price=0, sales=100)]
        self.assertEqual(select(items), [])


class TestAgentAndBridge(unittest.TestCase):
    def test_agent_find_returns_picks(self):
        picks = SourcingAgent(OneboundClient(api_key="")).find("蓝牙耳机", top_k=3)
        self.assertTrue(picks)
        self.assertLessEqual(len(picks), 3)
        self.assertTrue(all(p.resale_price > p.item.cost_price for p in picks))
        self.assertTrue(all(p.reason for p in picks))

    def test_bridge_to_promo_product(self):
        picks = SourcingAgent(OneboundClient(api_key="")).find("蓝牙耳机", top_k=1)
        prod = to_promo_product(picks[0], category="数码好物")
        self.assertIsInstance(prod, Product)
        self.assertEqual(prod.price, picks[0].resale_price)
        self.assertEqual(prod.category, "数码好物")
        self.assertTrue(prod.selling_points)
        self.assertNotIn("厂家直供", prod.title)   # 进货噪声词已去除


if __name__ == "__main__":
    unittest.main()
