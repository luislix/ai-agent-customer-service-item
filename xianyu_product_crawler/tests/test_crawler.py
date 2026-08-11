from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from xianyu_product_crawler.crawl import collect
from xianyu_product_crawler.models import CrawlConfig
from xianyu_product_crawler.models import SearchPage
from xianyu_product_crawler.outputs import write_outputs
from xianyu_product_crawler.providers.base import ProviderError
from xianyu_product_crawler.providers.fixture import FixtureProvider
from xianyu_product_crawler.redact import redact


ROOT = Path(__file__).resolve().parents[1]


class CrawlerTests(unittest.TestCase):
    def setUp(self):
        self.provider = FixtureProvider(ROOT / "fixtures/provider.json")

    def test_keyword_dedupe_and_limit(self):
        records, failures, _ = collect(["手机", "耳机", "手机"], self.provider, self.provider, CrawlConfig(per_keyword_limit=2, total_limit=3, page_size=1, delay_seconds=0))
        self.assertEqual([row["item_id"] for row in records], ["A1", "B2", "C3"])
        self.assertEqual(failures, [])

    def test_missing_fields_and_negotiable_price_are_empty(self):
        records, _, _ = collect(["耳机"], self.provider, self.provider, CrawlConfig(per_keyword_limit=2, total_limit=2, page_size=2, delay_seconds=0))
        item = next(row for row in records if row["item_id"] == "B2")
        self.assertIsNone(item["price"])
        self.assertIsNone(item["faq"])
        self.assertIsNone(item["shipping"])

    def test_stage_one_fields_are_emitted_with_legacy_aliases(self):
        records, _, _ = collect(["手机"], self.provider, self.provider, CrawlConfig(per_keyword_limit=1, total_limit=1, delay_seconds=0))
        item = records[0]
        self.assertEqual(item["specifications"], {"容量": "128GB", "颜色": "午夜黑"})
        self.assertEqual(item["specs"], item["specifications"])
        self.assertEqual(item["pricing"], {"sale_price": "2999", "currency": "CNY"})
        self.assertEqual(item["price"], item["pricing"])
        self.assertIsNone(item["category"])
        self.assertIsNone(item["included_items"])

    def test_redaction_removes_secrets_and_phone(self):
        safe = redact({"Cookie": "abc", "payload": "联系 13812345678"})
        self.assertEqual(safe["Cookie"], "[REDACTED]")
        self.assertNotIn("13812345678", safe["payload"])

    def test_outputs_are_jsonl_and_error_report(self):
        records, failures, raw = collect(["手机"], self.provider, self.provider, CrawlConfig(per_keyword_limit=1, total_limit=1, page_size=1, delay_seconds=0))
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            write_outputs(records, failures, raw, output=base / "snapshots.jsonl", markdown=base / "review.md", errors=base / "errors.jsonl", raw_dir=base / "raw")
            row = json.loads((base / "snapshots.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(row["item_id"], "A1")
            self.assertTrue((base / "raw/A1.json").exists())

    def test_retryable_provider_error_is_retried(self):
        class Flaky:
            def __init__(self):
                self.calls = 0

            def search(self, keyword, cursor, page_size):
                self.calls += 1
                if self.calls == 1:
                    raise ProviderError("temporary network failure")
                return SearchPage([])

            def get_detail(self, item_id):
                raise AssertionError("详情不应被调用")

        provider = Flaky()
        records, failures, _ = collect(["手机"], provider, provider, CrawlConfig(delay_seconds=0, retry_backoff_seconds=0, max_retries=1), sleep=lambda _: None)
        self.assertEqual(provider.calls, 2)
        self.assertEqual(records, [])
        self.assertEqual(failures, [])

    def test_authentication_failure_stops_immediately(self):
        class Unauthorized:
            def search(self, keyword, cursor, page_size):
                raise ProviderError("授权 API HTTP 401")

            def get_detail(self, item_id):
                raise AssertionError("详情不应被调用")

        with self.assertRaisesRegex(RuntimeError, "认证失败"):
            collect(["手机"], Unauthorized(), Unauthorized(), CrawlConfig(delay_seconds=0, max_retries=3), sleep=lambda _: None)


if __name__ == "__main__":
    unittest.main()
