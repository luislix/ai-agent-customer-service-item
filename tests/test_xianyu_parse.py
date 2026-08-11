"""用 DRY-RUN 实测抓到的【真实闲鱼消息结构】做离线回放，验证解析/过滤/取itemId。

数据来自真实监听日志（买家"怎么" + 闲鱼系统安全提示 + 已读回执同步包），
不依赖网络/XianYuApis，零风控风险。
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.modules.customer.xianyu_live_adapter import (  # noqa: E402
    find_item_id, find_peer_id, parse_buyer_message, parse_order_event,
)

# 1) 真实买家文本消息（contentType=1）
REAL_BUYER_MSG = {
    "1": {
        "1": {"1": "2641349279@goofish"},
        "2": "62848980868@goofish",
        "6": {"1": 101, "3": {"2": "怎么", "4": 1}},
        "10": {
            "reminderContent": "怎么",
            "reminderTitle": "买家昵称",
            "reminderUrl": "fleamarket://message_chat?itemId=1061218593323&peerUserId=2641349279&sid=62848980868&messageId=xxx&adv=no",
            "senderUserId": "2641349279",
            "senderUserType": "0",
        },
    },
    "3": {"needPush": "true"},
}

# 2) 闲鱼系统安全提示（contentType=14，bizTag 含 SECURITY）——应过滤
SYSTEM_SECURITY_MSG = {
    "1": {
        "2": "62848980868@goofish",
        "6": {"1": 101, "3": {"2": "请谨防诈骗", "4": 14}},
        "10": {
            "reminderContent": "喜欢的宝贝先咨询…谨防诈骗",
            "reminderTitle": "买家昵称",
            "bizTag": '{"sourceId":"SECURITY:utkOUb6lJQb3"}',
            "senderUserId": "2641349279",
        },
    },
}

# 3) 已读回执/同步包（结构对不上 m["1"]["10"]）——应过滤
READ_RECEIPT = {"1": ["4169448190894.PNM"], "2": 2, "3": "62848980868@goofish"}

# 4) 订单「已付款」系统消息（contentType!=1，含订单状态文案）——应识别为 paid
#    注：字段路径按已摸清的文本消息结构推断，真机抓到后用 XIANYU_DEBUG_DUMP=1 核对微调。
ORDER_PAID_MSG = {
    "1": {
        "2": "62848980868@goofish",
        "6": {"1": 101, "3": {"2": "买家已付款，等待您发货", "4": 26}},
        "10": {
            "reminderContent": "买家已付款，等待您发货",
            "reminderTitle": "交易提醒",
            "reminderUrl": "fleamarket://order_detail?itemId=1061218593323&peerUserId=2641349279&orderId=99",
            "bizTag": '{"sourceId":"ORDER:abc"}',
        },
    },
}

# 5) 「等待买家付款」系统消息——尚未付款，绝不能触发发货
ORDER_UNPAID_MSG = {
    "1": {
        "2": "62848980868@goofish",
        "6": {"1": 101, "3": {"2": "买家已拍下，等待买家付款", "4": 26}},
        "10": {
            "reminderContent": "买家已拍下，等待买家付款",
            "reminderTitle": "交易提醒",
            "reminderUrl": "fleamarket://order_detail?itemId=1061218593323&peerUserId=2641349279",
        },
    },
}


class TestXianyuParse(unittest.TestCase):
    def test_real_buyer_message_parsed(self):
        raw = parse_buyer_message(REAL_BUYER_MSG, myid="2222671721707")
        self.assertIsNotNone(raw)
        self.assertEqual(raw["text"], "怎么")
        self.assertEqual(raw["buyer_id"], "2641349279")
        self.assertEqual(raw["conversation_id"], "62848980868")

    def test_item_id_extracted_from_reminderurl(self):
        self.assertEqual(find_item_id(REAL_BUYER_MSG), "1061218593323")

    def test_system_security_message_filtered(self):
        # bug 修复点：闲鱼自动安全提示不应被当作买家消息回复
        self.assertIsNone(parse_buyer_message(SYSTEM_SECURITY_MSG, myid="2222671721707"))

    def test_read_receipt_filtered(self):
        self.assertIsNone(parse_buyer_message(READ_RECEIPT, myid="2222671721707"))

    def test_own_message_filtered(self):
        # 把发送者设成自己，应过滤（防自言自语死循环）
        self.assertIsNone(parse_buyer_message(REAL_BUYER_MSG, myid="2641349279"))


class TestOrderEvent(unittest.TestCase):
    def test_paid_event_recognized(self):
        ev = parse_order_event(ORDER_PAID_MSG)
        self.assertIsNotNone(ev)
        self.assertEqual(ev["event"], "paid")
        self.assertEqual(ev["item_id"], "1061218593323")
        self.assertEqual(ev["buyer_id"], "2641349279")     # peerUserId
        self.assertEqual(ev["conversation_id"], "62848980868")

    def test_unpaid_event_not_triggered(self):
        # 「等待买家付款」绝不能误判为已付款（否则会错误触发发货）
        self.assertIsNone(parse_order_event(ORDER_UNPAID_MSG))

    def test_buyer_text_is_not_order_event(self):
        # 普通买家文本不应被当成订单事件
        self.assertIsNone(parse_order_event(REAL_BUYER_MSG))

    def test_find_peer_id(self):
        self.assertEqual(find_peer_id(ORDER_PAID_MSG), "2641349279")


if __name__ == "__main__":
    unittest.main()
