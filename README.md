# 闲鱼智能客服 AI Agent

一个以“AI 辅助 + 人工兜底”为原则的电商自动化项目，当前包含三个相互隔离的业务模块：

- **客服**：闲鱼私信接入、意图识别、回复草稿、阶梯议价、实物发货工单。
- **选品**：1688/拼多多货源搜索、渠道利润测算、每日选品清单和人工审核。
- **推广**：中文小红书 / 英文 TikTok 文案，以及基于 Chrome/Edge 的图片卡片渲染。

公共编排层负责健康探针、`AUTO`/`MANUAL` 状态切换、工单落库和告警。任一外部平台失效时，相关模块会暂停自动动作，其他模块继续运行。

## 当前状态

已可运行：

- Python 标准库脚手架、状态机、SQLite 工单队列和 Phase 0 体检。
- 选品到推广的离线/真实 API 演示链路。
- 客服 Agent、LLM 抽象层、闲鱼实时桥接和安全降级。
- 商品 RAG 的 JSONL 校验、标准化、切片、`item_id` 隔离和 pgvector 导入接口。

仍需在真实环境验证：闲鱼协议稳定性、真实商品问法召回率、实时库存/价格 Provider、自动发布和生产级人工后台。规划内容见 [`docs/product-rag/商品RAG改造实施计划.md`](docs/product-rag/商品RAG改造实施计划.md) 和归档方案文档。

## 快速开始

```bash
# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate              # Windows: .venv\\Scripts\\activate

# 离线测试只需 pytest；真实接入/RAG 再安装完整依赖
python -m pip install pytest
# python -m pip install -r requirements.txt

# 复制配置模板，按需填写凭证；不要提交 .env
cp .env.example .env                  # Windows: copy .env.example .env

# 运行全部测试
python -m pytest -q

# 跑 Phase 0 接通体检；未配置凭证的模块显示 SKIPPED
python -m scripts.run_phase0_check
```

不配置任何外部凭证也可以运行离线测试和选品 demo：

```bash
python -m scripts.run_sourcing_demo 手机支架
python -m scripts.run_sourcing_demo 手机支架 --promo
python -m scripts.run_customer_sim
```

常驻每日选品和人工控制台：

```bash
python -m scripts.run_daily_sourcing
python -m scripts.run_scheduler
python -m scripts.run_console                   # http://127.0.0.1:8000
```

## 文档导航

| 文档 | 用途 |
|---|---|
| [`docs/README.md`](docs/README.md) | 文档索引和阅读顺序 |
| [`docs/architecture.md`](docs/architecture.md) | 当前架构、模块边界和状态流转 |
| [`docs/configuration.md`](docs/configuration.md) | `.env` 配置参考 |
| [`docs/operations/运行手册.md`](docs/operations/运行手册.md) | 启动、验证、定时任务和排障 |
| [`docs/operations/闲鱼安全测试清单.md`](docs/operations/闲鱼安全测试清单.md) | 闲鱼低频验证和风控应对 |
| [`xianyu_product_crawler/README.md`](xianyu_product_crawler/README.md) | 独立商品快照采集器 |
| [`docs/product-rag/商品RAG知识库技术方案.md`](docs/product-rag/商品RAG知识库技术方案.md) | RAG 架构和数据流 |
| [`docs/product-rag/商品快照JSONL接口规范.md`](docs/product-rag/商品快照JSONL接口规范.md) | 外部快照输入契约 |
| [`docs/product-rag/商品RAG验收测试方案.md`](docs/product-rag/商品RAG验收测试方案.md) | RAG 验收标准 |
| [`docs/product-rag/商品RAG改造实施计划.md`](docs/product-rag/商品RAG改造实施计划.md) | 后续改造计划 |
| [`docs/archive/`](docs/archive/) | 历史调研和早期总体方案，仅作背景参考 |

## 目录约定

```text
src/                         业务代码和编排层
scripts/                     可执行脚本
tests/                       主项目测试
xianyu_product_crawler/     独立商品快照采集器
docs/                        当前文档、RAG 资料和历史归档
data/                        本地运行数据；仅提交 example/测试样例
vendor/                      外部 XianYuApis 仓库，不纳入本项目版本库
```

`data/` 中的数据库、商品快照、图片和采集结果均为本地运行产物；`.gitignore` 只放行可复现的 example 和合成测试文件。`vendor/XianYuApis` 是独立第三方仓库，使用闲鱼实时桥接前需按运行手册单独准备。

## 合规边界

闲鱼、小红书和抖音接入依赖逆向协议或浏览器自动化，平台更新、验证码和封号风险无法消除。请使用合法商品和授权数据源，低频运行，先用 `--dry-run` 验证；发货、公开发帖、售后和价格承诺保留人工确认。商用前还需单独评估第三方依赖许可证和平台规则。
