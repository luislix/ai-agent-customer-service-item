import unittest

from scripts.enrich_keyword_dataset_for_test import enrich_row
from xianyu_product_crawler.validate import validate_snapshot


class TestKeywordDatasetEnrichment(unittest.TestCase):
    def _row(self, title, description):
        return {
            "item_id": "TEST-1",
            "title": title,
            "description": description,
            "source_url": "https://www.goofish.com/item?id=TEST-1",
            "updated_at": "2026-08-11T00:00:00Z",
        }

    def test_promotes_explicit_facts_and_builds_faq(self):
        row = enrich_row(self._row(
            "全新包邮手机直播支架",
            "最高1.6m，材质是金属，拍下24小时内发货，售出非质量问题不退不换，8.88元。",
        ))

        self.assertEqual(row["condition"], "全新")
        self.assertEqual(row["specs"]["最高高度"], "1.6m")
        self.assertEqual(row["pricing"]["sale_price"], "8.88")
        self.assertTrue(row["shipping"]["free_shipping"])
        self.assertEqual(row["shipping"]["dispatch_sla_hours"], 24)
        self.assertIn("不退不换", row["after_sale"])
        self.assertTrue(any(item["question"] == "包邮吗？多久发货？" for item in row["faq"]))

    def test_does_not_invent_unknown_inventory_or_shipping(self):
        row = enrich_row(self._row("普通手机支架", "材质为塑料，详情请咨询。"))

        self.assertIsNone(row["inventory"])
        self.assertIsNone(row["shipping"])
        self.assertIsNone(row["pricing"])
        self.assertTrue(row["faq"])

    def test_enriched_record_stays_within_snapshot_contract(self):
        row = enrich_row(self._row(
            "全新包邮耳机",
            "苹果安卓通用，续航5-6小时，现货，包邮。",
        ))

        normalized = validate_snapshot(row)
        self.assertEqual(normalized["inventory"]["status"], "in_stock")
        self.assertEqual(normalized["shipping"]["free_shipping"], True)
        self.assertGreaterEqual(len(normalized["faq"]), 3)


if __name__ == "__main__":
    unittest.main()
