"""PostgreSQL + pgvector 适配器。

依赖 psycopg 仅在实例化时导入，未安装时不影响纯单元测试和现有脚手架。
"""
from __future__ import annotations

from datetime import datetime, timezone


class PgVectorKnowledgeStore:
    def __init__(self, dsn: str, embedding_model: str = "BAAI/bge-m3", embedding_dimension: int = 1024, allow_model_reset: bool = False):
        try:
            import psycopg  # type: ignore
        except ImportError as exc:
            raise RuntimeError("生产 pgvector 需要安装 psycopg") from exc
        self.psycopg = psycopg
        self.dsn = dsn
        self.embedding_model = embedding_model
        self.embedding_dimension = embedding_dimension
        self.allow_model_reset = allow_model_reset
        self._init_schema()

    def _connect(self):
        return self.psycopg.connect(self.dsn)

    def _init_schema(self):
        # 向量维度由首批 embedding 决定，使用 vector 而非固定 vector(n) 以兼容不同模型。
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cur.execute("""CREATE TABLE IF NOT EXISTS product_rag_snapshots (
                snapshot_id TEXT PRIMARY KEY, item_id TEXT NOT NULL, snapshot_hash TEXT NOT NULL,
                source_url TEXT NOT NULL, updated_at TIMESTAMPTZ NOT NULL,
                is_current BOOLEAN NOT NULL DEFAULT TRUE, imported_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )""")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_product_rag_snapshots_item ON product_rag_snapshots(item_id, is_current)")
            cur.execute("""CREATE TABLE IF NOT EXISTS product_rag_chunks (
                chunk_id TEXT PRIMARY KEY, item_id TEXT NOT NULL, snapshot_id TEXT NOT NULL,
                kind TEXT NOT NULL, content TEXT NOT NULL, embedding vector,
                is_dynamic BOOLEAN NOT NULL DEFAULT FALSE, valid_until TIMESTAMPTZ,
                source_url TEXT NOT NULL, updated_at TIMESTAMPTZ NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_product_rag_item ON product_rag_chunks(item_id)")
            cur.execute("CREATE TABLE IF NOT EXISTS product_rag_embedding_meta (key TEXT PRIMARY KEY, model TEXT NOT NULL, dimension INTEGER NOT NULL)")
            cur.execute("SELECT model, dimension FROM product_rag_embedding_meta WHERE key='current'")
            meta = cur.fetchone()
            if meta and (meta[0] != self.embedding_model or meta[1] != self.embedding_dimension):
                if not self.allow_model_reset:
                    raise RuntimeError(f"数据库向量模型不匹配：已有 {meta[0]}/{meta[1]}，当前 {self.embedding_model}/{self.embedding_dimension}；请使用 --reindex 重建")
                cur.execute("DELETE FROM product_rag_chunks")
                cur.execute("DELETE FROM product_rag_snapshots")
                cur.execute("UPDATE product_rag_embedding_meta SET model=%s, dimension=%s WHERE key='current'", (self.embedding_model, self.embedding_dimension))
            if not meta:
                cur.execute("SELECT 1 FROM product_rag_chunks LIMIT 1")
                has_old_vectors = cur.fetchone() is not None
                if has_old_vectors and not self.allow_model_reset:
                    raise RuntimeError("数据库已有未标记模型的旧向量；请清空商品 RAG 向量后使用 --reindex 重建")
                if has_old_vectors and self.allow_model_reset:
                    cur.execute("DELETE FROM product_rag_chunks")
                    cur.execute("DELETE FROM product_rag_snapshots")
                cur.execute("INSERT INTO product_rag_embedding_meta(key,model,dimension) VALUES ('current',%s,%s)", (self.embedding_model, self.embedding_dimension))
            conn.commit()

    def replace_snapshot(self, item_id, snapshot_id, chunks, force=False):
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM product_rag_chunks WHERE item_id=%s AND snapshot_id=%s LIMIT 1", (item_id, snapshot_id))
            if cur.fetchone() and not force: return False
            first = chunks[0] if chunks else None
            snapshot_hash = snapshot_id.rsplit(":", 1)[-1]
            cur.execute("UPDATE product_rag_snapshots SET is_current=FALSE WHERE item_id=%s", (item_id,))
            if first:
                cur.execute("""INSERT INTO product_rag_snapshots
                    (snapshot_id,item_id,snapshot_hash,source_url,updated_at,is_current)
                    VALUES (%s,%s,%s,%s,%s,TRUE)
                    ON CONFLICT (snapshot_id) DO UPDATE SET is_current=TRUE""",
                    (snapshot_id, item_id, snapshot_hash, first.source_url, first.updated_at))
            cur.execute("DELETE FROM product_rag_chunks WHERE item_id=%s", (item_id,))
            for c in chunks:
                cur.execute("""INSERT INTO product_rag_chunks
                    (chunk_id,item_id,snapshot_id,kind,content,embedding,is_dynamic,valid_until,source_url,updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (c.chunk_id, c.item_id, c.snapshot_id, c.kind, c.content, list(c.embedding), c.is_dynamic, c.valid_until, c.source_url, c.updated_at))
            conn.commit()
            return True

    def has_snapshot(self, item_id, snapshot_id):
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM product_rag_chunks WHERE item_id=%s AND snapshot_id=%s LIMIT 1", (item_id, snapshot_id))
            return cur.fetchone() is not None

    def retrieve(self, item_id, query_embedding, top_k, min_score):
        now = datetime.now(timezone.utc)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT item_id,chunk_id,kind,content,1-(embedding <=> %s::vector) AS score,
                source_url,snapshot_id,updated_at,is_dynamic,valid_until
                FROM product_rag_chunks
                WHERE item_id=%s AND (valid_until IS NULL OR valid_until>%s)
                  AND 1-(embedding <=> %s::vector) >= %s
                ORDER BY (kind='faq') DESC, embedding <=> %s::vector
                LIMIT %s""", (query_embedding, item_id, now, query_embedding, min_score, query_embedding, top_k))
            from .contracts import RetrievedChunk
            return [RetrievedChunk(*row) for row in cur.fetchall()]
