# 文档索引

文档按用途分层。先读当前架构，再按任务进入通用运行手册或具体模块手册；`contracts/` 是稳定接口和验收标准，`plans/` 不代表当前已实现。

## 当前系统

- [`架构说明.md`](架构说明.md)：系统边界、数据流、状态机和模块协作。
- [`配置说明.md`](配置说明.md)：`.env` 变量、默认值和凭证来源。

## 通用运行

- [`operations/运行手册.md`](operations/运行手册.md)：安装、离线验证、调度、控制台和通用排障。
- [`operations/闲鱼安全测试清单.md`](operations/闲鱼安全测试清单.md)：闲鱼实时私信的低频验证纪律和风控处理。

## 独立模块

- [`modules/客服模块手册.md`](modules/客服模块手册.md)：客服模块的输入、回复、议价和人工兜底。
- [`modules/选品模块手册.md`](modules/选品模块手册.md)：选品、利润计算、审核和快照落库。
- [`modules/推广模块手册.md`](modules/推广模块手册.md)：小红书/微信内容生成、审核和渠道交付。
- [`modules/商品RAG模块手册.md`](modules/商品RAG模块手册.md)：商品知识库当前能力、导入和检索边界。
- [`modules/商品快照采集器手册.md`](modules/商品快照采集器手册.md)：授权商品快照采集器的使用入口。

## 稳定契约

- [`contracts/商品快照JSONL接口规范.md`](contracts/商品快照JSONL接口规范.md)：商品快照 JSONL 输入规范。
- [`contracts/商品RAG验收测试方案.md`](contracts/商品RAG验收测试方案.md)：RAG 导入、检索隔离和客服安全验收。

## 后续计划与历史

- [`plans/商品RAG改造实施计划.md`](plans/商品RAG改造实施计划.md)：RAG 后续改造计划，不作为当前操作步骤。
- [`archive/`](archive/)：历史调研和早期总体方案，仅用于了解决策背景。
