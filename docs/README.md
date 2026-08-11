# 文档索引

建议先阅读根目录 [`README.md`](../README.md)，再按任务选择下面的文档。当前实现和历史规划分开维护，避免把尚未落地的方案误认为已有能力。

## 快速上手

- [`operations/运行手册.md`](operations/运行手册.md)：安装、离线验证、真实凭证接入、定时任务和排障。
- [`configuration.md`](configuration.md)：`.env` 变量、默认值和凭证来源。
- [`operations/闲鱼安全测试清单.md`](operations/闲鱼安全测试清单.md)：闲鱼实时私信的低频验证纪律和风控处理。

## 当前实现参考

- [`architecture.md`](architecture.md)：编排层、客服、选品、推广和商品采集器的边界。
- [`product-rag/商品RAG知识库技术方案.md`](product-rag/商品RAG知识库技术方案.md)：RAG 目标、依赖方向和降级规则。
- [`product-rag/商品快照JSONL接口规范.md`](product-rag/商品快照JSONL接口规范.md)：快照字段、校验和版本兼容。
- [`product-rag/商品RAG验收测试方案.md`](product-rag/商品RAG验收测试方案.md)：导入、检索隔离和客服安全验收。
- [`../xianyu_product_crawler/README.md`](../xianyu_product_crawler/README.md)：授权商品快照采集器和 Chrome 扩展。

## 后续计划

- [`product-rag/商品RAG改造实施计划.md`](product-rag/商品RAG改造实施计划.md)：实时事实、混合检索、可信回答和分批上线计划。

## 历史资料

- [`archive/闲鱼智能客服AI-Agent调研报告.md`](archive/闲鱼智能客服AI-Agent调研报告.md)：2026-06 调研结论和外部信源。
- [`archive/方案设计_架构与落地路线图.md`](archive/方案设计_架构与落地路线图.md)：早期三模块总体方案和路线图。

历史资料用于解释决策背景；如与代码或当前文档冲突，以代码、接口规范和运行手册为准。
