"""独立的商品 RAG 知识库模块。

该包只负责商品快照导入、事实切片、向量检索和有效期过滤；不依赖客服、闲鱼或 LLM
生成模块。客服只通过 :mod:`contracts` 中的检索协议接入。
"""

from .contracts import (
    EmbeddingProvider,
    ImportReport,
    KnowledgeChunk,
    ProductKnowledgeRetriever,
    RetrievedChunk,
)
from .service import ProductRagService
from .manual_ingestion import KnowledgeDraft, KnowledgeDraftInput, ManualKnowledgeIngestion, ManualKnowledgeIngestionStore

__all__ = [
    "EmbeddingProvider",
    "ImportReport",
    "KnowledgeChunk",
    "ProductKnowledgeRetriever",
    "RetrievedChunk",
    "ProductRagService",
    "KnowledgeDraft",
    "KnowledgeDraftInput",
    "ManualKnowledgeIngestion",
    "ManualKnowledgeIngestionStore",
]
