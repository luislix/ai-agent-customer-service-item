"""闲鱼实时私信桥接层：把已验证的 CustomerServiceAgent 接到 XianYuApis 上。

为什么是"桥接"而不是"重写协议"：
  闲鱼实时私信 = WebSocket + Protobuf 同步包 + 需 Node.js 执行的 JS 签名算法，
  完整实现依赖 cv-cat/XianYuApis（goofish_live.py 负责 WS 收发，goofish_apis.py 负责
  登录/token/发送）。本项目不重复造这个轮子，而是把 XianYuApis 当作"传输层"，
  在它的"收到买家消息 -> 你来决定回什么"回调点接入我们的 Agent。

集成步骤（在能访问 GitHub 的机器上）：
  1. git clone https://github.com/cv-cat/XianYuApis.git
  2. cd XianYuApis && pip install -r requirements.txt   # 另需 Node.js 18+ 跑 JS 签名
  3. 把本项目可 import，或把本文件的 build_reply_handler 复制过去
  4. 在 XianYuApis 的 goofish_live 回复回调里调用本模块的 reply handler

安全默认：DRY_RUN=True 时只生成草稿不发送，先人工验证质量与稳定性，再开实发。
"""
from __future__ import annotations

from collections.abc import Callable

from ...core.state_machine import ModuleStateMachine
from ...core.work_order import WorkOrderStore
from ...llm.base import LLMClient
from .agent import CustomerServiceAgent
from .types import AgentReply, BuyerMessage
from ..product_rag.contracts import ProductKnowledgeRetriever

# 把 XianYuApis 收到的原始消息（dict）映射成我们的 BuyerMessage 的解析器类型。
# 不同版本 XianYuApis 字段名可能不同，这里用可替换的 resolver，集成时按实际字段调整。
MessageResolver = Callable[[dict], BuyerMessage]


def default_resolver(raw: dict) -> BuyerMessage:
    """把 XianYuApis 的消息 dict 映射为 BuyerMessage。

    注意：字段名以 XianYuApis 实际输出为准，下面是常见命名的兜底取值，集成时核对调整。
    """
    return BuyerMessage(
        conversation_id=str(raw.get("conversation_id") or raw.get("cid") or raw.get("sessionId") or ""),
        buyer_id=str(raw.get("buyer_id") or raw.get("sender") or raw.get("fromId") or ""),
        text=str(raw.get("text") or raw.get("content") or raw.get("message") or ""),
        item_id=str(raw.get("item_id") or raw.get("itemId") or ""),
        item_title=str(raw.get("item_title") or raw.get("itemTitle") or ""),
        item_price=float(raw.get("item_price") or raw.get("price") or 0) or 0.0,
        floor_price=float(raw.get("floor_price") or 0) or 0.0,
        is_virtual=bool(raw.get("is_virtual") or False),
        paid=bool(raw.get("paid") or raw.get("isPaid") or False),
    )


class XianyuLiveBridge:
    """把 Agent + 状态机 + 工单兜底，封装成一个"收到消息 -> 返回该发的回复文本"的回调。

    直接把 bridge.handle_raw 作为 XianYuApis goofish_live 的 AI 回复函数即可。
    """

    def __init__(
        self,
        llm: LLMClient,
        store: WorkOrderStore,
        sm: ModuleStateMachine,
        resolver: MessageResolver = default_resolver,
        dry_run: bool = True,
        retriever: ProductKnowledgeRetriever | None = None,
    ):
        self.agent = CustomerServiceAgent(llm, retriever)
        self.store = store
        self.sm = sm
        self.resolver = resolver
        self.dry_run = dry_run

    def handle_raw(self, raw: dict) -> str | None:
        """XianYuApis 收到买家消息时调用本方法。

        返回值：要发送的回复文本；返回 None 表示"不发送"（降级转人工 / DRY_RUN）。
        """
        msg = self.resolver(raw)

        # 降级状态：不自动回，转人工工单（人工兜底，消息不丢）
        if not self.sm.is_auto:
            self.store.create(
                "customer", "reply_message",
                {"conversation_id": msg.conversation_id, "buyer_id": msg.buyer_id, "text": msg.text},
                reason="客服模块降级，转人工回复",
            )
            return None

        reply: AgentReply = self.agent.handle(msg)
        self._apply_actions(msg, reply)

        if self.dry_run:
            # 安全默认：只生成草稿，打印给人看，不真正发送
            print(f"[DRY-RUN 草稿] 会话{msg.conversation_id} 意图={reply.intent.value} "
                  f"动作={reply.actions}\n  -> {reply.text}")
            return None
        return reply.text

    def handle_paid_event(
        self,
        conversation_id: str,
        buyer_id: str,
        item_id: str,
        item_title: str = "",
        is_virtual: bool = False,
    ) -> str | None:
        """收到「已付款」订单事件：走发货流程（建工单 + 确认话术）。

        返回给买家的确认文本；DRY_RUN/降级返回 None（不发送）。
        is_virtual 默认 False -> 实物建人工发货工单（安全，不自动采购/发货）。
        """
        # 降级：不自动回，直接建人工发货工单（消息不丢）
        if not self.sm.is_auto:
            self.store.create(
                "customer", "ship_order",
                {"conversation_id": conversation_id, "item_id": item_id, "buyer_id": buyer_id},
                reason="客服模块降级，已付款待人工发货",
            )
            return None

        msg = BuyerMessage(
            conversation_id=conversation_id, buyer_id=buyer_id,
            text="[系统]买家已付款", item_id=item_id,
            item_title=item_title, is_virtual=is_virtual, paid=True,
        )
        reply = self.agent.handle(msg)   # route -> PURCHASE -> auto_ship / create_ship_order
        self._apply_actions(msg, reply)

        if self.dry_run:
            print(f"[DRY-RUN 已付款] 会话{conversation_id} 动作={reply.actions}\n  -> {reply.text}")
            return None
        return reply.text

    def _apply_actions(self, msg: BuyerMessage, reply: AgentReply) -> None:
        for action in reply.actions:
            if action == "auto_ship":
                self.store.create("customer", "auto_ship_done",
                                  {"conversation_id": msg.conversation_id, "item_id": msg.item_id},
                                  reason="虚拟商品自动发货")
            elif action == "create_ship_order":
                self.store.create("customer", "ship_order",
                                  {"conversation_id": msg.conversation_id,
                                   "item_id": msg.item_id, "buyer_id": msg.buyer_id},
                                  reason="实物已付款，待人工发货")
            elif action == "escalate_human":
                self.store.create("customer", "human_followup",
                                  {"conversation_id": msg.conversation_id, "text": msg.text},
                                  reason="售后/投诉转人工")
