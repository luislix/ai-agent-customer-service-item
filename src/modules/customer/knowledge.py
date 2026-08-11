"""商品知识库与轻量检索。

默认使用 JSON 文件和词法匹配，适合当前客服模块的单进程部署。检索器接口保持
独立，后续可用 pgvector/Milvus 实现同样的 ``retrieve`` 方法而无需改 Agent。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class KnowledgeDocument:
    item_id: str
    content: str
    title: str = ""
    kind: str = "product"
    source: str = ""


@dataclass(frozen=True)
class RetrievedDocument:
    document: KnowledgeDocument
    score: float


class ProductKnowledgeBase:
    """商品资料的可信来源。

    JSON 格式支持 ``documents``，也支持更适合人工维护的 ``products``：
    ``{"products": [{"item_id": "A1", "title": "...", "specs": {...},
    "faq": [{"question": "...", "answer": "..."}]}]}``。
    """

    def __init__(self, documents: list[KnowledgeDocument] | None = None):
        self.documents = list(documents or [])

    @classmethod
    def default(cls, root: str | Path | None = None) -> "ProductKnowledgeBase":
        """加载 data/product_knowledge.json；文件不存在时返回空库。"""
        project_root = Path(root) if root is not None else Path(__file__).resolve().parents[3]
        return cls.from_json(project_root / "data" / "product_knowledge.json")

    @classmethod
    def from_json(cls, path: str | Path) -> "ProductKnowledgeBase":
        source = Path(path)
        if not source.exists():
            return cls()
        with source.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        docs: list[KnowledgeDocument] = []
        for raw in payload.get("documents", []) if isinstance(payload, dict) else []:
            if not isinstance(raw, dict) or not raw.get("item_id") or not raw.get("content"):
                continue
            docs.append(KnowledgeDocument(
                item_id=str(raw["item_id"]), content=str(raw["content"]),
                title=str(raw.get("title") or ""), kind=str(raw.get("kind") or "product"),
                source=str(raw.get("source") or source.name),
            ))
        for product in payload.get("products", []) if isinstance(payload, dict) else []:
            if not isinstance(product, dict) or not product.get("item_id"):
                continue
            item_id = str(product["item_id"])
            title = str(product.get("title") or "")
            facts = []
            for field in ("specs", "condition", "inventory", "price", "shipping", "after_sale"):
                value = product.get(field)
                if value not in (None, "", {}, []):
                    facts.append(f"{field}: {_flatten(value)}")
            if facts:
                docs.append(KnowledgeDocument(item_id, "；".join(facts), title, "product", source.name))
            for faq in product.get("faq", []) or []:
                if isinstance(faq, dict) and faq.get("answer"):
                    question = str(faq.get("question") or "")
                    docs.append(KnowledgeDocument(
                        item_id, f"问题：{question}\n标准答案：{faq['answer']}", title, "faq", source.name,
                    ))
        return cls(docs)

    def retrieve(self, item_id: str, query: str, top_k: int = 4) -> list[RetrievedDocument]:
        """按商品限定范围检索；未传 item_id 时不会把别的商品资料混入回答。"""
        candidates = [d for d in self.documents if not item_id or d.item_id == str(item_id)]
        if not candidates:
            return []
        terms = _terms(query)
        ranked = []
        for doc in candidates:
            haystack = f"{doc.title} {doc.content}".lower()
            hits = sum(1 for term in terms if term in haystack)
            # FAQ 的问题和标题命中更有价值；没有命中时不作为事实注入。
            score = float(hits)
            if doc.kind == "faq":
                score += sum(0.25 for term in terms if term in doc.content.split("\n", 1)[0].lower())
            if score > 0:
                ranked.append(RetrievedDocument(doc, score))
        ranked.sort(key=lambda x: x.score, reverse=True)
        return ranked[:max(0, top_k)]

    def context(self, query: str, item_id: str = "", top_k: int = 4) -> str:
        results = self.retrieve(item_id=item_id, query=query, top_k=top_k)
        if not results:
            return "（知识库没有找到与该商品问题匹配的可靠资料，不要自行补充参数或承诺。）"
        return "\n".join(
            f"[{r.document.kind}:{r.document.source or r.document.item_id}] {r.document.content}"
            for r in results
        )


def _flatten(value: Any) -> str:
    if isinstance(value, dict):
        return "，".join(f"{k}={_flatten(v)}" for k, v in value.items())
    if isinstance(value, list):
        return "、".join(_flatten(v) for v in value)
    return str(value)


def _terms(text: str) -> list[str]:
    # 中文按连续字符片段匹配，英文/数字按词匹配；短词仍保留以支持“库存/颜色”等问题。
    parts = re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z0-9][a-zA-Z0-9._-]*", text.lower())
    terms = set(parts)
    for part in parts:
        if len(part) > 2 and re.fullmatch(r"[\u4e00-\u9fff]+", part):
            terms.update(part[i:i + 2] for i in range(len(part) - 1))
    return list(terms)
