"""LLM 抽象层：统一 chat() 接口，便于在通义千问/Claude/占位之间切换。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ChatMessage:
    role: str   # system / user / assistant
    content: str


class LLMClient:
    """所有 LLM 实现的统一接口。"""

    name: str = "base"

    def chat(self, messages: list[ChatMessage], temperature: float = 0.7) -> str:
        raise NotImplementedError

    @property
    def available(self) -> bool:
        """是否具备真实调用条件（如已配 API key）。"""
        return True
