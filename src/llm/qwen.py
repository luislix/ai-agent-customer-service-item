"""通义千问（DashScope OpenAI 兼容端点）客户端，纯标准库实现，无需安装 SDK。

需要 .env 配置 DASHSCOPE_API_KEY。未配置时 available=False，由工厂回退到占位实现。
"""
from __future__ import annotations

import json
import urllib.request

from .base import ChatMessage, LLMClient

_ENDPOINT = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"


class QwenClient(LLMClient):
    name = "qwen"

    def __init__(
        self,
        api_key: str | None,
        model: str = "qwen-plus",
        endpoint: str = _ENDPOINT,
    ):
        self.api_key = api_key
        self.model = model
        self.endpoint = endpoint

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def chat(self, messages: list[ChatMessage], temperature: float = 0.7) -> str:
        if not self.available:
            raise RuntimeError("未配置 DASHSCOPE_API_KEY")
        payload = json.dumps({
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
        }).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"].strip()
