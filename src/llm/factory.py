"""LLM 工厂：按配置选 provider，凭证缺失时自动回退到占位实现并告知。"""
from __future__ import annotations

from ..config import config
from .base import LLMClient
from .placeholder import PlaceholderClient
from .openai_compatible import OpenAICompatibleClient
from .qwen import QwenClient


def build_llm() -> LLMClient:
    provider = (config.LLM_PROVIDER or "qwen").lower()
    if provider == "qwen":
        client = QwenClient(config.QWEN_API_KEY, model=config.QWEN_MODEL, endpoint=config.QWEN_ENDPOINT)
        if client.available:
            return client
    if provider == "deepseek":
        client = OpenAICompatibleClient(
            config.DEEPSEEK_API_KEY,
            config.DEEPSEEK_ENDPOINT,
            config.DEEPSEEK_MODEL,
            "deepseek",
        )
        if client.available:
            return client
    # 其它 provider（claude/local）可在此扩展
    return PlaceholderClient()
