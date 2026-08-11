import json
import tempfile
import unittest
from pathlib import Path

from src.modules.product_rag.xianyu_snapshot_crawler import (
    CrawlFailure,
    crawl_details,
    discover_item_links,
    normalize_item_detail,
    render_markdown,
    write_outputs,
)


DETAIL = {
    "data": {"itemDO": {"title": "测试耳机", "desc": "蓝牙耳机", "soldPrice": "39.9"}}
}


class TestXianyuSnapshotCrawler(unittest.TestCase):
    def test_discover_deduplicates_urls_and_ids(self):
        items = discover_item_links([
            "https://www.goofish.com/item?id=1234567890",
            "https://www.goofish.com/item?itemId=1234567890",
            "1234567891",
        ], limit=20)
        self.assertEqual([item.item_id for item in items], ["1234567890", "1234567891"])

    def test_normalize_detail_and_private_price(self):
        record = normalize_item_detail("1234567890", "https://www.goofish.com/item?id=1234567890", DETAIL)
        self.assertEqual(record["title"], "测试耳机")
        self.assertEqual(record["price"]["sale_price"], "39.9")
        private = {"data": {"itemDO": {"title": "面议商品", "defaultPrice": True, "soldPrice": "99999999"}}}
        record = normalize_item_detail("1234567891", "https://www.goofish.com/item?id=1234567891", private)
        self.assertIsNone(record["price"])

    def test_ignores_non_contract_specs(self):
        detail = {"data": {"itemDO": {**DETAIL["data"]["itemDO"], "props": ["非标准规格"]}}}
        record = normalize_item_detail("1234567890", "https://www.goofish.com/item?id=1234567890", detail)
        self.assertIsNone(record["specs"])

    def test_extracts_sku_specs_and_explicit_free_shipping(self):
        detail = {"data": {"itemDO": {
            **DETAIL["data"]["itemDO"],
            "skuList": [{"propertyList": [{"propertyText": "容量", "actualValueText": "128GB"}]}],
            "priceRelativeTags": [{"text": "包邮"}],
        }}}
        record = normalize_item_detail("1234567890", "https://www.goofish.com/item?id=1234567890", detail)
        self.assertEqual(record["specs"], {"容量": "128GB"})
        self.assertEqual(record["shipping"]["fee"], "0.00")

    def test_bad_detail_does_not_stop_batch(self):
        items = discover_item_links(["1234567890", "1234567891"])
        records, failures = crawl_details(items, lambda item_id: DETAIL if item_id.endswith("0") else {})
        self.assertEqual(len(records), 1)
        self.assertEqual(failures[0].item_id, "1234567891")

    def test_outputs_markdown_and_errors(self):
        record = normalize_item_detail("1234567890", "https://www.goofish.com/item?id=1234567890", DETAIL)
        failure = CrawlFailure("1234567891", "detail", "下架")
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "snapshots.jsonl"
            markdown = Path(td) / "snapshots.md"
            errors = Path(td) / "errors.jsonl"
            write_outputs([record], [failure], output=output, markdown=markdown, errors=errors)
            self.assertEqual(len(output.read_text(encoding="utf-8").splitlines()), 1)
            self.assertIn(record["source_url"], markdown.read_text(encoding="utf-8"))
            self.assertIn("1234567891", errors.read_text(encoding="utf-8"))
            json.loads(output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
