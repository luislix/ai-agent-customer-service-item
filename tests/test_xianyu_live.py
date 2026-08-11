"""闲鱼实时桥接测试：DRY-RUN 不发送、降级转工单、动作落库。用占位 LLM，不联网。"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.state_machine import ModuleStateMachine  # noqa: E402
from src.core.work_order import WorkOrderStore  # noqa: E402
from src.llm.placeholder import PlaceholderClient  # noqa: E402
from src.modules.customer.xianyu_live import XianyuLiveBridge, default_resolver  # noqa: E402

RAW = {"conversation_id": "c1", "buyer_id": "b1", "text": "能便宜点吗",
       "item_title": "测试商品", "price": 100, "floor_price": 80}


class TestXianyuLiveBridge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = WorkOrderStore(str(Path(self.tmp.name) / "t.db"))
        self.sm = ModuleStateMachine("customer")

    def tearDown(self):
        self.tmp.cleanup()

    def test_resolver_maps_fields(self):
        msg = default_resolver(RAW)
        self.assertEqual(msg.conversation_id, "c1")
        self.assertEqual(msg.item_price, 100.0)
        self.assertEqual(msg.floor_price, 80.0)

    def test_dry_run_does_not_return_text(self):
        bridge = XianyuLiveBridge(PlaceholderClient(), self.store, self.sm, dry_run=True)
        self.assertIsNone(bridge.handle_raw(RAW))  # DRY-RUN 不发送

    def test_live_returns_text(self):
        bridge = XianyuLiveBridge(PlaceholderClient(), self.store, self.sm, dry_run=False)
        out = bridge.handle_raw(RAW)
        self.assertIsInstance(out, str)
        self.assertTrue(out)

    def test_manual_state_creates_work_order_and_no_send(self):
        self.sm.force_manual("协议失效")
        bridge = XianyuLiveBridge(PlaceholderClient(), self.store, self.sm, dry_run=False)
        self.assertIsNone(bridge.handle_raw(RAW))             # 降级不发
        self.assertTrue(self.store.list_pending("customer"))  # 转工单

    def test_physical_paid_creates_ship_order(self):
        bridge = XianyuLiveBridge(PlaceholderClient(), self.store, self.sm, dry_run=False)
        raw = {**RAW, "text": "付款了", "paid": True, "is_virtual": False}
        bridge.handle_raw(raw)
        self.assertTrue(any(w.action == "ship_order"
                            for w in self.store.list_pending("customer")))

    def test_paid_event_creates_ship_order_and_replies(self):
        # 订单「已付款」系统事件 -> 实物建发货工单 + 返回确认话术
        bridge = XianyuLiveBridge(PlaceholderClient(), self.store, self.sm, dry_run=False)
        text = bridge.handle_paid_event("c9", "b9", "item9", item_title="测试商品")
        self.assertIsInstance(text, str)
        self.assertTrue(any(w.action == "ship_order"
                            for w in self.store.list_pending("customer")))

    def test_paid_event_virtual_auto_ships(self):
        bridge = XianyuLiveBridge(PlaceholderClient(), self.store, self.sm, dry_run=False)
        bridge.handle_paid_event("c8", "b8", "item8", is_virtual=True)
        self.assertTrue(any(w.action == "auto_ship_done"
                            for w in self.store.list_pending("customer")))

    def test_paid_event_dry_run_no_text(self):
        bridge = XianyuLiveBridge(PlaceholderClient(), self.store, self.sm, dry_run=True)
        self.assertIsNone(bridge.handle_paid_event("c7", "b7", "item7"))

    def test_paid_event_manual_creates_ship_order(self):
        self.sm.force_manual("协议失效")
        bridge = XianyuLiveBridge(PlaceholderClient(), self.store, self.sm, dry_run=False)
        self.assertIsNone(bridge.handle_paid_event("c6", "b6", "item6"))
        self.assertTrue(any(w.action == "ship_order"
                            for w in self.store.list_pending("customer")))


if __name__ == "__main__":
    unittest.main()
