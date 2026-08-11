"""OpenAI-compatible chat completion client for interchangeable providers."""
from __future__ import annotations

import json
import urllib.request

from .base import ChatMessage, LLMClient


class OpenAICompatibleClient(LLMClient):
    """Minimal standard-library client shared by DeepSeek, Qwen, and compatible APIs."""

    def __init__(self, api_key: str | None, endpoint: str, model: str, name: str):
        self.api_key = api_key
        self.endpoint = endpoint
        self.model = model
        self.name = name

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def chat(self, messages: list[ChatMessage], temperature: float = 0.7) -> str:
        if not self.available:
            raise RuntimeError(f"未配置 {self.name} API key")
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
