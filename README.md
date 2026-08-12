# 闲鱼智能客服 AI Agent

一个以“AI 辅助 + 人工兜底”为原则的电商自动化项目，包含客服、选品、推广和商品知识库模块。公共编排层负责健康探针、`AUTO`/`MANUAL` 状态切换、工单和告警；任一外部平台失效时，相关模块暂停自动动作，其他模块继续运行。

## 当前能力

- 客服：闲鱼私信接入、意图识别、商品事实问答、回复草稿、阶梯议价和人工工单。
- 选品：1688/拼多多货源搜索、渠道利润测算、每日选品清单和人工审核。
- 推广：小红书图文发布包、微信服务号草稿，以及小红书浏览器自动填充（最终公开发布仍人工确认）。
- 商品知识库：JSONL 校验、标准化、事实切片、`item_id` 隔离和 pgvector 导入接口。

仍需真实环境验证：闲鱼协议稳定性、真实商品问法召回率、实时库存/价格 Provider、微信接口权限、小红书发布风控和生产级运营后台。

## 快速开始

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install pytest
cp .env.example .env
python -m pytest -q
python -m scripts.run_phase0_check
```

无外部凭证时也可以运行离线演示：

```bash
python -m scripts.run_sourcing_demo 手机支架
python -m scripts.run_customer_sim
python -m scripts.run_console              # http://127.0.0.1:8000
```

## 文档

从 [`docs/README.md`](docs/README.md) 开始。文档按“当前架构、通用运行、独立模块、稳定契约、后续计划、历史资料”分层；模块文档只描述自身能力，不重复全局配置和安装步骤。

## 合规边界

闲鱼、小红书和抖音接入依赖逆向协议或浏览器自动化，平台更新、验证码和封号风险无法消除。请使用合法商品和授权数据源，低频运行，先用 `--dry-run` 验证；发货、公开发帖、售后和价格承诺保留人工确认。商用前还需评估第三方依赖许可证和平台规则。
