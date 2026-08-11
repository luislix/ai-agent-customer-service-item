"""闲鱼客服 Agent：意图路由 + 拟人化回复 + 阶梯议价 + 动作决策。

设计对齐调研里的 XianyuAutoAgent 思路（专家分诊 + 阶梯降价），但用我们自己的
LLM 抽象与状态管理，便于接状态机/工单兜底。

- 意图路由：关键词快判 + （可选）LLM 兜底，分到议价/咨询/物流/售后/已付款等场景。
- 拟人化回复：按场景注入不同 system prompt，口语化、简短、带闲鱼买卖习惯。
- 阶梯议价：按会话维护让价档位，不越过 floor_price 下限。
- 动作决策：识别"已付款"→ 触发发货（虚拟品自动 / 实物建人工工单）；识别售后/投诉 → 转人工。
"""
from __future__ import annotations

from ..customer.types import AgentReply, BuyerMessage, Intent
from ...llm.base import ChatMessage, LLMClient
from ..product_rag.contracts import ProductKnowledgeRetriever
from ..product_rag.null import NullRetriever

_PERSONA = (
    "你是闲鱼上一位友好、真诚、说话口语化的二手卖家客服。"
    "回复要简短(1-3句)、自然、像真人，多用'亲''哈''~'，不要像机器人，不要长篇大论。"
)

_INTENT_PROMPT = {
    Intent.GREETING: "买家在打招呼，热情回应并主动询问需求。",
    Intent.PRODUCT_QA: "买家在咨询商品(参数/成色/库存)，基于商品标题如实、简洁回答，不确定就说帮他确认。",
    Intent.LOGISTICS: "买家关心发货/物流，只能依据商品知识库中的物流事实回答；没有资料或资料过期就明确说需要确认。",
    Intent.AFTERSALE: "买家在反映售后/质量问题，先共情安抚，表示会负责处理。",
    Intent.PURCHASE: "买家已拍下/付款，表达感谢并告知马上安排发货。",
    Intent.OTHER: "正常友好回应买家。",
}

_KW = {
    Intent.BARGAIN: ("便宜", "少点", "降", "优惠", "包邮", "最低", "刀", "能少"),
    Intent.LOGISTICS: ("发货", "什么时候", "多久", "快递", "几天", "物流", "到货"),
    Intent.AFTERSALE: ("退", "换", "坏", "问题", "假", "差评", "投诉", "瑕疵"),
    Intent.PURCHASE: ("拍了", "付了", "已付款", "下单", "付款了", "拍下"),
    Intent.PRODUCT_QA: ("成色", "参数", "尺寸", "颜色", "库存", "还有", "新旧", "多少钱", "配置"),
    Intent.GREETING: ("在吗", "在不在", "你好", "在么", "在"),
}


class CustomerServiceAgent:
    def __init__(self, llm: LLMClient, retriever: ProductKnowledgeRetriever | None = None):
        self.llm = llm
        # RAG 基础设施由组合层注入；Agent 不读取文件、不创建数据库连接。
        self.retriever = retriever or NullRetriever()
        # 每个会话的议价让价次数（阶梯议价用）
        self._bargain_rounds: dict[str, int] = {}

    # ---- 意图路由 ----
    def route(self, msg: BuyerMessage) -> Intent:
        if msg.paid:
            return Intent.PURCHASE
        t = msg.text
        # 优先级：已付款 > 售后 > 议价 > 物流 > 咨询 > 打招呼
        for intent in (Intent.PURCHASE, Intent.AFTERSALE, Intent.BARGAIN,
                       Intent.LOGISTICS, Intent.PRODUCT_QA, Intent.GREETING):
            if any(k in t for k in _KW[intent]):
                return intent
        return Intent.OTHER

    # ---- 主入口 ----
    def handle(self, msg: BuyerMessage) -> AgentReply:
        intent = self.route(msg)
        if intent is Intent.BARGAIN:
            return self._handle_bargain(msg)
        if intent is Intent.AFTERSALE:
            # 售后默认转人工，避免 AI 乱承诺
            text = self._llm_reply(msg, intent)
            return AgentReply(text=text, intent=intent, actions=["escalate_human"])
        if intent is Intent.PURCHASE:
            return self._handle_purchase(msg)
        text = self._llm_reply(msg, intent)
        return AgentReply(text=text, intent=intent)

    # ---- 阶梯议价 ----
    def _handle_bargain(self, msg: BuyerMessage) -> AgentReply:
        rounds = self._bargain_rounds.get(msg.conversation_id, 0)
        self._bargain_rounds[msg.conversation_id] = rounds + 1

        # 无下限或下限>=标价：不让价，礼貌坚持
        if msg.floor_price <= 0 or msg.floor_price >= msg.item_price > 0:
            text = self._llm_reply(msg, Intent.BARGAIN,
                                   extra="价格已是实价，礼貌婉拒降价，可强调商品价值/包邮等。")
            return AgentReply(text=text, intent=Intent.BARGAIN)

        # 阶梯让价：把 标价->下限 的空间按档位逐步释放（最多 3 档）
        span = msg.item_price - msg.floor_price
        steps = [0.4, 0.7, 1.0]  # 第1/2/3次砍价分别让到 40%/70%/100% 的可让空间
        ratio = steps[min(rounds, len(steps) - 1)]
        offer = round(msg.item_price - span * ratio, 2)
        offer = max(offer, msg.floor_price)
        text = self._llm_reply(
            msg, Intent.BARGAIN,
            extra=f"你可以让步到 {offer} 元(不能更低)。用口语自然地给出这个价，营造'诚意价'的感觉。",
        )
        return AgentReply(text=text, intent=Intent.BARGAIN,
                          actions=[f"offer_price:{offer}"])

    # ---- 已付款 → 触发发货 ----
    def _handle_purchase(self, msg: BuyerMessage) -> AgentReply:
        text = self._llm_reply(msg, Intent.PURCHASE)
        if msg.is_virtual:
            # 虚拟商品可自动发货
            return AgentReply(text=text, intent=Intent.PURCHASE,
                              actions=["auto_ship"])
        # 实物：建人工发货工单，不自动下单采购
        return AgentReply(text=text, intent=Intent.PURCHASE,
                          actions=["create_ship_order"])

    # ---- 调 LLM 生成拟人回复 ----
    def _llm_reply(self, msg: BuyerMessage, intent: Intent, extra: str = "") -> str:
        sys_prompt = _PERSONA + " " + _INTENT_PROMPT.get(intent, "")
        if extra:
            sys_prompt += " " + extra
        ctx = f"商品：《{msg.item_title}》标价 {msg.item_price} 元。" if msg.item_title else ""
        ctx += "\n商品知识库（仅可依据以下资料回答；没有资料就明确说不确定）：\n"
        ctx += self._knowledge_context(msg.item_id, msg.text)
        messages = [
            ChatMessage("system", sys_prompt),
            ChatMessage("user", f"{ctx}买家说：{msg.text}"),
        ]
        try:
            return self.llm.chat(messages)
        except Exception as e:  # noqa: BLE001 LLM 失败不应崩，降级提示
            return f"亲稍等下哈~（AI 回复暂不可用：{e}）"

    def _knowledge_context(self, item_id: str, query: str) -> str:
        if not item_id:
            return "（缺少商品 ID，不能回答具体商品事实，请让买家提供商品链接或转人工确认。）"
        try:
            results = self.retriever.retrieve(item_id=item_id, query=query, top_k=5)
        except Exception as e:  # noqa: BLE001 RAG 不可用时安全降级
            return f"（商品知识库暂不可用：{e}；不要猜测商品事实，请转人工确认。）"
        if not results:
            return "（知识库没有找到与该商品问题匹配的可靠资料，不要自行补充参数或承诺。）"
        lines = []
        for result in results:
            source = getattr(result, "source_url", "") or getattr(result, "document", None)
            content = getattr(result, "content", None)
            if content is None and source is not None:
                content = getattr(source, "content", "")
                source = getattr(source, "source", "")
            lines.append(f"[{getattr(result, 'kind', 'product')}:{source}] {content}")
        return "\n".join(lines)
