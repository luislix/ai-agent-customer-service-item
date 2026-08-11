# 商品 RAG 知识库技术方案

## 1. 目标与边界

商品 RAG 为客服 Agent 提供按 `item_id` 隔离的可靠商品事实。爬虫是外部系统，本项目只接收 JSONL 快照并负责校验、标准化、切片、Embedding、存储和检索。

本模块不负责闲鱼爬虫、图片理解、商品后台、自动改价、自动发货或售后判断；议价底价、发货工单和售后转人工仍由现有客服规则负责。

独立数据生产模块位于仓库顶层 `xianyu_product_crawler/`。它只接入授权 API、明确允许的页面数据源或手动 URL，输出 JSONL、脱敏原始 fixture 和人工审阅报告；不会读取本模块的 Cookie、访问 RAG 数据库或自动触发导入。现有 `src/modules/product_rag/xianyu_snapshot_crawler.py` 仅保留为历史/指定 URL 实验流程，不作为新采集模块的依赖。

## 2. 独立模块设计

代码位于 `src/modules/product_rag/`，对外只暴露 `contracts.py` 的 `ProductKnowledgeRetriever`、`ProductRagImporter`、`RetrievedChunk` 等契约。客服 Agent 只依赖检索协议，不能创建数据库、读取文件或初始化 Embedding。具体实现由应用组合层注入。

依赖方向：`customer → product_rag.contracts`；`product_rag.service → repository / embedding`。不允许 `customer → PostgreSQL/pgvector/本地模型/JSON 路径`。

## 3. 数据流

```text
外部爬虫 JSONL → 校验 → canonical 标准化 → 快照哈希 → 业务切片
→ Embedding → PostgreSQL + pgvector → item_id 过滤 → 相似度检索 → Agent Prompt
```

## 4. 校验与标准化

- 每行必须是 JSON object，单行最大 256KB；单条错误写入错误报告，不中断整批。
- `item_id` 必填，长度 1-64，只允许字母、数字、`-`、`_`。
- `title` 必填，长度 1-200；HTML 清理后不能只有标点。
- `updated_at` 必须是带时区 ISO-8601，未来超过 10 分钟拒绝，入库统一 UTC。
- `source_url` 必须为 `http/https`，最大 2048 字符。
- 规格只能是标量或标量数组；库存状态为 `in_stock/out_of_stock/unknown`；价格使用 Decimal；FAQ 最多 100 条。
- canonical JSON 对字典排序、数组去重、空字段归一化；`SHA256(canonical_json_without_updated_at)` 作为快照哈希。

## 5. 事实切片

固定切片类型：`basic_info`、`specification`、`commercial`、`shipping`、`after_sale`、`faq`。每条 FAQ 独立切片；长文本超过 800 字符时按段落/句子切分，目标 600-800 字符、重叠 80 字符，不跨字段或商品切分。只有明确 `free_shipping=true`、发货时效、快递或非零运费才生成 `shipping` chunk；单独的 `fee=0` 默认值不视为包邮事实。

每个 chunk 带 `item_id`、快照 ID、类型、来源、更新时间、动态标记和 `valid_until`。库存、售价、发货时效、快递、运费默认 24 小时有效；过期动态事实不进入检索结果。`floor_price` 不进入 RAG。

## 6. 存储与检索

生产使用 PostgreSQL + pgvector，保存快照和 chunk 元数据。检索必须先 `item_id` 硬过滤，再过滤当前版本和 TTL，最后按 cosine 相似度排序；默认 `top_k=5`、最低分 `0.50`（按 bge-m3 中文客服问法校准），FAQ 优先。无 `item_id`、低分、冲突或 RAG 不可用时不得猜测，转为确认/人工处理。

## 7. Embedding 与 Agent 接入

Embedding 通过 `EmbeddingProvider` 协议注入，生产默认使用 `sentence-transformers` 本地模型 `BAAI/bge-m3`（1024 维）；不依赖 DashScope 账户。Agent 通过 `ProductKnowledgeRetriever.retrieve(item_id, query, top_k)` 获取事实，并要求 DeepSeek 只依据事实回答；RAG 不产生客服动作。

开发和测试可使用 `NullRetriever`、`InMemoryKnowledgeStore` 和 Fake Embedding；生产装配由 `product_rag.factory` 完成。

## 8. 导入与配置

```bash
python -m scripts.ingest_product_snapshots products.jsonl --errors import.errors.jsonl
# 真实导入前先校验和预览切片，不连接数据库
python -m scripts.ingest_product_snapshots products.jsonl --validate-only --preview chunks.preview.jsonl
```

关键配置：`RAG_ENABLED`、`RAG_DATABASE_URL`、`RAG_EMBEDDING_MODEL_PATH`、`RAG_EMBEDDING_DEVICE`、`RAG_EMBEDDING_BATCH_SIZE`、`RAG_TOP_K`、`RAG_MIN_SCORE`。缺少数据库配置时使用空检索器，不影响旧客服链路。Embedding 模型首次运行需要下载并占用本机 CPU/内存/磁盘；切换模型后必须使用导入脚本的 `--reindex` 重建旧向量。

## 9. 安全、降级与上线

商品资料按数据处理，不能执行其中的指令；Prompt 中明确禁止商品文本改变系统规则。导入失败保留旧版本；过期动态事实不使用；数据库或 Embedding 不可用时不生成具体商品承诺。上线顺序为离线召回评测、Dry-run、小流量、再扩大范围。

## 10. 后续扩展

可替换为本地 Embedding、Milvus、图片理解或管理后台，但只能实现对应接口，不改变客服模块契约。
