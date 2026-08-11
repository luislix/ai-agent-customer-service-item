"""工单队列测试：降级动作落库不丢、人工处理完成。"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.work_order import WorkOrderStore  # noqa: E402


class TestWorkOrder(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = WorkOrderStore(str(Path(self.tmp.name) / "t.db"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_create_and_list(self):
        oid = self.store.create("customer", "ship_order",
                                {"order_id": "A123"}, reason="协议失效降级")
        self.assertGreater(oid, 0)
        pending = self.store.list_pending()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].payload["order_id"], "A123")  # 数据不丢

    def test_complete(self):
        oid = self.store.create("promotion", "publish_post", {"title": "测款"})
        self.assertTrue(self.store.complete(oid))
        self.assertEqual(self.store.count_pending(), 0)
        self.assertFalse(self.store.complete(oid))  # 重复完成无效

    def test_filter_by_module(self):
        self.store.create("customer", "reply", {})
        self.store.create("sourcing", "pick", {})
        self.assertEqual(self.store.count_pending("customer"), 1)
        self.assertEqual(self.store.count_pending("sourcing"), 1)


if __name__ == "__main__":
    unittest.main()
