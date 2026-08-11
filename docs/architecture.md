# 当前架构

## 范围

项目是一个 Python 模块化单体，外部平台接入以脚本方式运行。客服、选品和推广共享编排层，但业务代码不直接互相调用。SQLite 用于本地工单和选品清单；商品 RAG 生产部署可使用 PostgreSQL + pgvector。

```text
外部平台 / 本地 fixture
          |
          v
  客服 | 选品 | 推广 | 商品快照采集器
          |
          v
       Orchestrator
   探针 -> 状态机 -> 工单 -> 告警
          |
          v
       SQLite / RAG 存储
```

## 编排和故障兜底

`src/orchestrator.py` 注册三个模块探针：`customer`、`sourcing`、`promotion`。每次 `run_health_cycle()`：

1. 执行探针并得到 `OK`、`FAILED` 或 `SKIPPED`。
2. `FAILED` 连续达到 `HEALTH_FAIL_THRESHOLD` 后，状态从 `AUTO` 切换为 `MANUAL`。
3. 降级回调创建工单并通过 `ALERT_WEBHOOK` 告警；没有 webhook 时打印到控制台。
4. 探针恢复后默认仍需人工调用 `recover_module()` 才回到 `AUTO`。

`SKIPPED` 表示未配置凭证，不计入失败。工单写入 `DB_PATH` 指向的 SQLite 文件，状态为 `pending`、`done` 或 `cancelled`。

## 业务模块

### 客服

入口是 `src/modules/customer/` 和 `scripts/run_xianyu_live.py`。Agent 负责意图路由、回复生成、议价和人工动作；`XianyuLiveBridge` 负责把外部消息转换为内部处理。实时模式依赖单独准备的 `vendor/XianYuApis`，推荐先用 `--dry-run`。

客服可注入 `ProductKnowledgeRetriever`。RAG 只提供按 `item_id` 隔离的商品事实，不负责议价底价、发货决策或售后权限；检索不可用时必须明确不确定并转人工。

### 选品

`src/modules/sourcing/` 通过 `SOURCING_PROVIDER` 选择 justoneapi 或 Onebound。`platforms.py` 使用平台档计算佣金、汇率、物流、退货和加价后的利润，并返回渠道比较结果。`daily_job.py` 将每日结果写入 SQLite，人工在控制台 approve/reject。

没有 token/key 时客户端使用离线样例，适合测试流程但不能代表真实货源质量。

### 推广

`src/modules/promotion/` 调用 LLM 生成中文或英文文案，再使用系统 Chrome/Edge 无头截图渲染 1080×1440 图片卡片。图片和正文默认写入 `data/`，属于运行产物，不提交版本库。自动公开发布尚未纳入当前核心实现。

### 商品快照采集器

`xianyu_product_crawler/` 是独立数据生产模块，只输出 JSONL 快照和审阅报告，不读取当前项目的 RAG 数据库或自动导入。采集器仅支持授权 API、fixture 和明确允许的页面采集；登录失效、验证码或安全验证会停止任务。

## RAG 数据流

```text
授权采集器 JSONL
  -> 逐行校验/标准化
  -> 快照哈希与事实切片
  -> Embedding
  -> PostgreSQL + pgvector
  -> item_id 硬过滤 + TTL + 相似度
  -> 客服 Agent 的可信上下文
```

动态库存、价格、物流等字段后续应由实时 Provider 提供，不能把过期向量结果当作当前事实。接口、字段和验收标准见 [`product-rag/商品快照JSONL接口规范.md`](product-rag/商品快照JSONL接口规范.md) 和 [`product-rag/商品RAG验收测试方案.md`](product-rag/商品RAG验收测试方案.md)。

## 代码边界

- `customer` 只依赖 `product_rag.contracts`，不能直接初始化 Embedding、读取 JSON 或连接 pgvector。
- `product_rag` 不负责平台爬虫、自动发货、自动改价或售后判断。
- `vendor/` 不属于本仓库版本边界；升级第三方库时要单独记录版本和许可证。
- `data/` 的运行状态不属于代码提交内容；只提交 example 和合成测试资料。
