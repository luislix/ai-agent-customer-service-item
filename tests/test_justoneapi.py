"""justoneapi 选品数据源测试：离线退化、容错解析、本地过滤、数据源切换（不需 token/网络）。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import config  # noqa: E402
from src.modules.sourcing import factory  # noqa: E402
from src.modules.sourcing.justoneapi_client import (  # noqa: E402
    JustOneApiClient, _apply_filter, _clean_title, _locate_rows, _parse_items,
)
from src.modules.sourcing.onebound_client import OneboundClient  # noqa: E402
from src.modules.sourcing.types import SourcedItem, SourcingQuery  # noqa: E402


class TestOffline(unittest.TestCase):
    def test_offline_when_no_token(self):
        c = JustOneApiClient(token="")
        self.assertFalse(c.available)
        items = c.search(SourcingQuery(keyword="保温杯"))
        self.assertTrue(items)
        self.assertTrue(all("保温杯" in it.title for it in items))


# 真实 1688 搜索返回结构：data.data.OFFER.items[i].data
_SAMPLE = {"code": "0", "data": {"data": {"OFFER": {"items": [
    {"data": {
        "offerId": 674035283676,
        "title": "跨境750ml大容量<font color=red>保温杯</font>不锈钢",
        "priceInfo": {"price": "16", "priceType": "NORMAL"},
        "afterPrice": {"text": "已售10万+件"},
        "bookedCount": 21843,
        "offerPicUrl": "https://a.alicdn.com/1.jpg,https://a.alicdn.com/2.jpg",
        "linkUrl": "https://detail.1688.com/offer/674035283676.html",
        "loginId": "迎庆杯业",
    }},
]}}}}


class TestParse(unittest.TestCase):
    def test_clean_title_strips_html(self):
        self.assertEqual(_clean_title("好货<font color=red>保温杯</font>"), "好货保温杯")

    def test_locate_rows_real_path(self):
        rows = _locate_rows(_SAMPLE)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["data"]["offerId"], 674035283676)

    def test_locate_rows_empty(self):
        self.assertEqual(_locate_rows({}), [])

    def test_parse_items_real_structure(self):
        items = _parse_items(_SAMPLE, "1688")
        self.assertEqual(len(items), 1)
        it = items[0]
        self.assertEqual(it.item_id, "674035283676")
        self.assertNotIn("<font", it.title)
        self.assertIn("保温杯", it.title)
        self.assertEqual(it.cost_price, 16.0)
        self.assertEqual(it.sales, 100000)            # 「已售10万+件」-> 10万
        self.assertEqual(it.pic_url, "https://a.alicdn.com/1.jpg")   # 取首张
        self.assertEqual(it.seller, "迎庆杯业")
        self.assertEqual(it.platform, "1688")

    def test_apply_filter(self):
        items = [
            SourcedItem(item_id="a", title="t", cost_price=10, sales=100),
            SourcedItem(item_id="b", title="t", cost_price=50, sales=5),
        ]
        q = SourcingQuery(keyword="x", max_price=20, min_sales=50)
        out = _apply_filter(items, q)
        self.assertEqual([it.item_id for it in out], ["a"])


class TestFactorySwitch(unittest.TestCase):
    def test_factory_picks_by_provider(self):
        orig = config.SOURCING_PROVIDER
        try:
            config.SOURCING_PROVIDER = "justoneapi"
            self.assertIsInstance(factory.make_sourcing_client(), JustOneApiClient)
            config.SOURCING_PROVIDER = "onebound"
            self.assertIsInstance(factory.make_sourcing_client(), OneboundClient)
        finally:
            config.SOURCING_PROVIDER = orig


if __name__ == "__main__":
    unittest.main()
