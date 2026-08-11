"""客服 Agent + 调度器测试：意图路由、阶梯议价、发货/售后动作、降级兜底。

用占位 LLM（不联网）保证测试稳定。
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.state_machine import ModuleStateMachine  # noqa: E402
from src.core.work_order import WorkOrderStore  # noqa: E402
from src.llm.placeholder import PlaceholderClient  # noqa: E402
from src.modules.customer.agent import CustomerServiceAgent  # noqa: E402
from src.modules.customer.channel import SimulatedChannel  # noqa: E402
from src.modules.customer.dispatcher import CustomerDispatcher  # noqa: E402
from src.modules.customer.types import BuyerMessage, Intent  # noqa: E402

ITEM = dict(item_id="A1", item_title="测试商品", item_price=100.0, floor_price=80.0)


class TestAgentRouting(unittest.TestCase):
    def setUp(self):
        self.agent = CustomerServiceAgent(PlaceholderClient())

    def test_route_intents(self):
        cases = {
            "在吗": Intent.GREETING,
            "能便宜点吗": Intent.BARGAIN,
            "成色怎么样": Intent.PRODUCT_QA,
            "什么时候发货": Intent.LOGISTICS,
            "要退货": Intent.AFTERSALE,
        }
        for text, expect in cases.items():
            msg = BuyerMessage("c", "b", text, **ITEM)
            self.assertIs(self.agent.route(msg), expect, text)

    def test_paid_routes_to_purchase(self):
        msg = BuyerMessage("c", "b", "随便说点", paid=True, **ITEM)
        self.assertIs(self.agent.route(msg), Intent.PURCHASE)

    def test_bargain_ladder_not_below_floor(self):
        # 连续砍价，让价逐步加深但永不低于 floor_price
        offers = []
        for _ in range(4):
            r = self.agent.handle(BuyerMessage("conv-x", "b", "便宜点", **ITEM))
            price = [a for a in r.actions if a.startswith("offer_price:")]
            self.assertTrue(price, "议价应给出 offer_price")
            offers.append(float(price[0].split(":")[1]))
        self.assertTrue(all(o >= ITEM["floor_price"] for o in offers), offers)
        self.assertLessEqual(offers[0], ITEM["item_price"])     # 有让价
        self.assertLessEqual(offers[-1], offers[0])             # 越砍越低（或持平）

    def test_no_discount_when_no_floor(self):
        item = dict(item_id="A", item_title="x", item_price=100.0, floor_price=0.0)
        r = self.agent.handle(BuyerMessage("c", "b", "便宜点", **item))
        self.assertFalse([a for a in r.actions if a.startswith("offer_price:")])

    def test_virtual_paid_auto_ship(self):
        msg = BuyerMessage("c", "b", "付款了", paid=True, is_virtual=True, **ITEM)
        r = self.agent.handle(msg)
        self.assertIn("auto_ship", r.actions)

    def test_physical_paid_creates_ship_order(self):
        msg = BuyerMessage("c", "b", "付款了", paid=True, is_virtual=False, **ITEM)
        r = self.agent.handle(msg)
        self.assertIn("create_ship_order", r.actions)

    def test_aftersale_escalates(self):
        r = self.agent.handle(BuyerMessage("c", "b", "要退货", **ITEM))
        self.assertIn("escalate_human", r.actions)


class TestDispatcher(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = WorkOrderStore(str(Path(self.tmp.name) / "t.db"))
        self.sm = ModuleStateMachine("customer")

    def tearDown(self):
        self.tmp.cleanup()

    def _dispatcher(self, inbox):
        ch = SimulatedChannel(inbox)
        return ch, CustomerDispatcher(ch, PlaceholderClient(), self.store, self.sm)

    def test_auto_reply_and_send(self):
        ch, d = self._dispatcher([BuyerMessage("c1", "b1", "在吗", **ITEM)])
        trace = d.run_once()
        self.assertEqual(trace[0]["handled"], "auto")
        self.assertEqual(len(ch.sent), 1)  # 回复已发出

    def test_physical_purchase_creates_work_order(self):
        ch, d = self._dispatcher([
            BuyerMessage("c1", "b1", "付款了", paid=True, is_virtual=False, **ITEM)])
        d.run_once()
        pending = self.store.list_pending("customer")
        self.assertTrue(any(w.action == "ship_order" for w in pending))

    def test_manual_state_routes_to_work_order(self):
        self.sm.force_manual("协议失效")
        ch, d = self._dispatcher([BuyerMessage("c1", "b1", "在吗", **ITEM)])
        trace = d.run_once()
        self.assertEqual(trace[0]["handled"], "manual")
        self.assertEqual(len(ch.sent), 0)  # 降级时不自动回
        self.assertTrue(self.store.list_pending("customer"))  # 转工单


if __name__ == "__main__":
    unittest.main()
