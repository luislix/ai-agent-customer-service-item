"""在应用组合层装配 RAG；客服模块不感知具体基础设施。"""
from __future__ import annotations

from ...config import config
from .null import NullRetriever
from .embedding import LocalBgeM3EmbeddingProvider


def build_retriever():
    if not config.RAG_ENABLED or not config.RAG_DATABASE_URL:
        return NullRetriever()
    from .pgvector_store import PgVectorKnowledgeStore
    from .service import ProductRagService

    embedding = LocalBgeM3EmbeddingProvider(config.RAG_EMBEDDING_MODEL_PATH, config.RAG_EMBEDDING_DEVICE, config.RAG_EMBEDDING_BATCH_SIZE)
    store = PgVectorKnowledgeStore(config.RAG_DATABASE_URL, embedding.model, embedding.dimension)
    return ProductRagService(store, embedding, config.RAG_TOP_K, config.RAG_MIN_SCORE)


def build_service(force_model_reset: bool = False):
    """返回可导入/检索的生产服务；配置不完整时明确报错。"""
    if not config.RAG_ENABLED or not config.RAG_DATABASE_URL:
        raise RuntimeError("RAG 导入需要开启 RAG_ENABLED，并配置 RAG_DATABASE_URL")
    from .pgvector_store import PgVectorKnowledgeStore
    from .service import ProductRagService
    embedding = LocalBgeM3EmbeddingProvider(config.RAG_EMBEDDING_MODEL_PATH, config.RAG_EMBEDDING_DEVICE, config.RAG_EMBEDDING_BATCH_SIZE)
    return ProductRagService(
        PgVectorKnowledgeStore(config.RAG_DATABASE_URL, embedding.model, embedding.dimension, allow_model_reset=force_model_reset),
        embedding,
        config.RAG_TOP_K,
        config.RAG_MIN_SCORE,
    )
