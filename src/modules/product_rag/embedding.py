"""商品 RAG 的 Embedding 适配器。

生产默认使用本地 ``BAAI/bge-m3``；DashScope 适配器保留给旧调用方兼容。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request


class LocalBgeM3EmbeddingProvider:
    """使用 sentence-transformers 在本机运行 BAAI/bge-m3。"""

    model = "BAAI/bge-m3"
    dimension = 1024

    def __init__(self, model_name: str | None = None, device: str = "auto", batch_size: int = 16):
        self.model_name = model_name or self.model
        self.device = device
        self.batch_size = batch_size
        self._model = None

    def _load(self):
        if self._model is not None:
            return self._model
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError("本地 BGE Embedding 需要安装 sentence-transformers 和 PyTorch") from exc
        try:
            device = self.device
            if device == "auto":
                try:
                    import torch
                    device = "cuda" if torch.cuda.is_available() else "cpu"
                except ImportError:
                    device = "cpu"
            self._model = SentenceTransformer(self.model_name, device=device)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"加载本地 Embedding 模型失败：{self.model_name}；请检查模型路径、网络和内存") from exc
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._load()
        try:
            vectors = model.encode(
                texts,
                batch_size=self.batch_size,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
            return [[float(value) for value in row] for row in vectors]
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("本地 BGE Embedding 编码失败，请检查输入长度和机器资源") from exc


class DashScopeEmbeddingProvider:
    def __init__(self, api_key: str | None, model: str = "text-embedding-v3", endpoint: str = "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings"):
        self.api_key, self.model, self.endpoint = api_key, model, endpoint

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not self.api_key:
            raise RuntimeError("未配置 DashScope Embedding API key")
        body = json.dumps({"model": self.model, "input": texts}).encode("utf-8")
        req = urllib.request.Request(self.endpoint, data=body, headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise RuntimeError(f"DashScope Embedding 请求失败（HTTP {exc.code}）：{detail}") from exc
        return [row["embedding"] for row in sorted(data["data"], key=lambda x: x["index"])]
