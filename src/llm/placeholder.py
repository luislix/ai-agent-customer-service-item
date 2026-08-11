"""占位 LLM：无 API key 时让整条回复流水线仍能跑通（基于意图的模板回复）。

不是为了拟人，而是为了在没配 key 时也能端到端验证 Agent/通道/调度逻辑。
配上真实 key 后，工厂会自动切换到通义千问/Claude。
"""
from __future__ import annotations

from .base import ChatMessage, LLMClient


class PlaceholderClient(LLMClient):
    name = "placeholder"

    @property
    def available(self) -> bool:
        return True

    def chat(self, messages: list[ChatMessage], temperature: float = 0.7) -> str:
        # 取最后一条 user 文本做极简规则回复
        user_text = ""
        for m in reversed(messages):
            if m.role == "user":
                user_text = m.content
                break
        t = user_text
        if any(k in t for k in ("便宜", "少点", "降", "优惠", "包邮")):
            return "亲，这个价格已经很实在啦~ 诚心要的话可以小刀，给您便宜 2 元，您看可以吗？"
        if any(k in t for k in ("发货", "什么时候", "多久", "快递")):
            return "亲，付款后我会尽快为您安排发货哈，一般当天就发出~"
        if any(k in t for k in ("在吗", "在不在", "你好", "在么")):
            return "在的亲~ 请问有什么可以帮您？"
        return "亲，您的问题我看到啦，方便详细说下吗？我帮您处理~ [占位回复：配置 DASHSCOPE_API_KEY 后启用真实 AI]"
