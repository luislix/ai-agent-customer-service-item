"""客服调度器：通道 -> Agent -> 回复，并接状态机/工单兜底。

闭环逻辑：
  从通道取买家消息
    -> 若客服模块处于 MANUAL（降级）：消息转人工工单，不自动回（人工兜底）
    -> 否则交给 Agent 生成回复，按动作处理：
         auto_ship          虚拟商品自动发货（记录，实际发货逻辑后续接）
         create_ship_order  实物 -> 建发货工单等人工
         escalate_human     售后等 -> 建转人工工单
       并通过通道把回复发出去
"""
from __future__ import annotations

from ...core.state_machine import ModuleStateMachine
from ...core.work_order import WorkOrderStore
from ...llm.base import LLMClient
from .agent import CustomerServiceAgent
from .channel import XianyuMessageChannel
from .types import AgentReply, BuyerMessage
from ..product_rag.contracts import ProductKnowledgeRetriever


class CustomerDispatcher:
    def __init__(
        self,
        channel: XianyuMessageChannel,
        llm: LLMClient,
        store: WorkOrderStore,
        sm: ModuleStateMachine,
        retriever: ProductKnowledgeRetriever | None = None,
    ):
        self.channel = channel
        self.agent = CustomerServiceAgent(llm, retriever)
        self.store = store
        self.sm = sm

    def run_once(self) -> list[dict]:
        """处理通道里当前所有待处理消息，返回处理轨迹（便于观测/测试）。"""
        trace = []
        for msg in self.channel.iter_messages():
            trace.append(self._process(msg))
        return trace

    def _process(self, msg: BuyerMessage) -> dict:
        # 降级状态：不自动回，转人工工单（人工兜底，消息不丢）
        if not self.sm.is_auto:
            oid = self.store.create(
                module="customer", action="reply_message",
                payload={"conversation_id": msg.conversation_id,
                         "buyer_id": msg.buyer_id, "text": msg.text},
                reason="客服模块降级，转人工回复",
            )
            return {"conversation": msg.conversation_id, "handled": "manual",
                    "work_order": oid}

        reply: AgentReply = self.agent.handle(msg)
        self._apply_actions(msg, reply)
        self.channel.send(msg.conversation_id, reply.text)
        return {
            "conversation": msg.conversation_id,
            "handled": "auto",
            "intent": reply.intent.value,
            "actions": reply.actions,
            "reply": reply.text,
        }

    def _apply_actions(self, msg: BuyerMessage, reply: AgentReply) -> None:
        for action in reply.actions:
            if action == "auto_ship":
                # 虚拟商品自动发货：此处记录，真实发货(发卡密/链接)后续接
                self.store.create("customer", "auto_ship_done",
                                  {"conversation_id": msg.conversation_id,
                                   "item_id": msg.item_id}, reason="虚拟商品自动发货")
            elif action == "create_ship_order":
                self.store.create("customer", "ship_order",
                                  {"conversation_id": msg.conversation_id,
                                   "item_id": msg.item_id, "buyer_id": msg.buyer_id},
                                  reason="实物已付款，待人工发货")
            elif action == "escalate_human":
                self.store.create("customer", "human_followup",
                                  {"conversation_id": msg.conversation_id,
                                   "text": msg.text}, reason="售后/投诉转人工")
            # offer_price:* 等动作目前仅体现在回复文案中，无需额外落库
