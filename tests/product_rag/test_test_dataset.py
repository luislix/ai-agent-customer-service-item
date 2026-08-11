import json
import tempfile
import unittest
from pathlib import Path

from scripts.generate_product_test_data import generate_eval_cases, generate_snapshots, write_jsonl
from src.modules.product_rag.validator import validate_and_normalize


class TestProductTestDataset(unittest.TestCase):
    def test_generates_complete_snapshots_and_eval_cases(self):
        snapshots = generate_snapshots(count=40, updated_at="2026-08-10T12:00:00+08:00")
        cases = generate_eval_cases(snapshots, questions_per_item=10)

        self.assertEqual(len(snapshots), 40)
        self.assertEqual(len({row["item_id"] for row in snapshots}), 40)
        self.assertEqual(len(cases), 400)
        self.assertEqual({row["item_id"] for row in cases}, {row["item_id"] for row in snapshots})
        for snapshot in snapshots:
            normalized = validate_and_normalize(snapshot)
            self.assertTrue(normalized["specifications"])
            self.assertTrue(normalized["included_items"])
            self.assertTrue(normalized["inventory"])
            self.assertTrue(normalized["pricing"])
            self.assertTrue(normalized["shipping"])
            self.assertTrue(normalized["after_sale"])
            self.assertEqual(len(normalized["faq"]), 10)
        self.assertTrue(all(case["synthetic"] for case in cases))
        self.assertTrue(sum(case["hard_negative_item_id"] is not None for case in cases) >= 40)

    def test_write_jsonl_creates_parent_and_round_trips(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "nested" / "snapshots.jsonl"
            write_jsonl(target, [{"item_id": "TEST-001", "title": "测试"}])
            self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["item_id"], "TEST-001")


if __name__ == "__main__":
    unittest.main()
