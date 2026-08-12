# 商品 RAG 模块

## 作用与边界

`src/modules/product_rag/` 负责商品事实快照的校验、规范化、哈希版本、切片、Embedding、向量存储和按商品检索。RAG 只提供经过验证的商品事实，不负责写营销文案、议价底价、自动发货或售后判断。

## 输入、依赖与数据

- 输入：符合 [`../contracts/商品快照JSONL接口规范.md`](../contracts/商品快照JSONL接口规范.md) 的 JSONL 快照。
- 依赖：本地 Embedding 模型和 PostgreSQL + pgvector（生产可选）；开发环境可用内存仓库或 `NullRetriever`。
- 数据流：校验/标准化 -> 快照哈希 -> 事实切片 -> Embedding -> 向量存储 -> `item_id` 硬过滤检索。

## 使用流程

先验证和预览，不连接数据库：

```bash
python -m scripts.ingest_product_snapshots products.jsonl \
  --validate-only --preview data/chunks.preview.jsonl \
  --errors data/import.errors.jsonl
```

确认数据后，配置 `RAG_ENABLED=true` 和 `RAG_DATABASE_URL` 再导入：

```bash
RAG_ENABLED=true python -m scripts.ingest_product_snapshots products.jsonl --reindex
```

## 安全边界

- 每次检索必须带 `item_id`，不同商品绝不互相召回。
- 动态价格、库存和物流信息必须检查有效期，过期或冲突时不得确定性回答。
- 商品知识遵循“草稿 -> 人工补全 -> 发布”，选品审核不会自动写入知识库。
- 没有命中、分数过低或 RAG 不可用时，客服应明确不确定并转人工。

## 关键入口与验证

- `src/modules/product_rag/contracts.py`：稳定协议。
- `src/modules/product_rag/validator.py`：输入校验。
- `src/modules/product_rag/service.py`：导入和检索编排。
- `src/modules/product_rag/manual_ingestion.py`：人工知识草稿。

验收标准见 [`../contracts/商品RAG验收测试方案.md`](../contracts/商品RAG验收测试方案.md)，后续改造见 [`../plans/商品RAG改造实施计划.md`](../plans/商品RAG改造实施计划.md)。
