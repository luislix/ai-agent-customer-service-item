# 闲鱼智能客服 AI Agent 系统 · 全网调研报告

> 调研时间：2026-06-22
> 方法：深度研究工作流（5 个检索角度 → 22 个信源抓取 → 79 条声明提取 → 25 条对抗式验证 → 24 条确认 / 1 条否决）
> 范围：闲鱼自动客服+发货、1688/拼多多自动选品、小红书/抖音自动发帖+AI 配图、合规风险

---

## 〇、总体结论（先看这个）

设想的三大模块**技术上全部可实现，且都已有现成开源项目 / 商业工具**。但有一条贯穿全局的红线：

> **闲鱼、小红书、抖音三个平台的接入，几乎全部依赖"逆向协议"或"浏览器自动化"，没有一个是平台官方授权的。** 平台一旦更新协议或风控，工具即失效甚至导致**封号**。所谓"无头/隐身/指纹伪装"只能缓解、不能消除检测。真正稳妥的落地形态是 **"AI 辅助 + 关键动作人工确认"的半自动化**，而非"全自动无人值守"。

此外，多数闲鱼/小红书开源项目带 **GPL/AGPL 协议或"仅供学习、请勿商用"声明**，商用前必须评估许可证和法律风险。

---

## 一、模块一：闲鱼自动客服 + 自动发货

### 1.1 推荐开源项目（按成熟度）

| 项目 | 技术栈 | 核心能力 | 协议 | 验证 |
|---|---|---|---|---|
| **XianyuAutoAgent**（约 8000 星，最成熟）| Python 3.8+ | 7×24 拟人化值守；LLM 提示工程 + 规则的**专家分诊**（议价/技术/客服三场景动态分发）；**阶梯降价智能议价** | GPL-3.0 | 3-0 ✓ |
| **xianyu-auto-reply**（全栈最完整）| FastAPI / SQLAlchemy / MySQL / Redis / Playwright | 自动回复、**自动发货**、自动评价、库存管理、客服自动化全套 | AGPL-3.0 | 2-1 ✓ |
| **XianYuAssistant**（Java 生态）| JDK21 / Spring Boot 3.5.7 / Spring AI / Vue3 | 付款后自动检测"已付款待发货"并**按配置自动发货**；集成**通义千问 Qwen + RAG 知识库**（需阿里云 API Key）| 仅供学习，请勿商用 | 3-0 ✓ |
| **xianyu-openclaw-channel** | WebSocket / SSE | 基于付款检测自动确认发货，作为 OpenClaw/Botpress 频道插件接入 | — | 3-0 ✓ |

**信源：**
- https://github.com/shaxiu/XianyuAutoAgent
- https://github.com/zhinianboke/xianyu-auto-reply
- https://github.com/IAMLZY2018/XianYuAssistant
- https://github.com/laozuzhen/xianyu-openclaw-channel

### 1.2 底层通信基座（关键）

上述项目的私信收发，普遍依赖 **`cv-cat/XianYuApis`**：

- 逆向还原了闲鱼 **WebSocket 私信协议**（`sign` 签名 + base64 编码 + Protobuf 序列化），可实时收发买家私信
- 预留了接 GPT/Claude/Qwen/本地模型的示例代码：`reply = await your_ai_agent(send_message)`
- 自我定位为"咸鱼 AI Agent 基座"
- **接入方式**：从闲鱼网页端 F12 拿 cookie → 连接接口。属逆向手段，**平台更新即可能失效**

> ⚠️ 通用 IM 机器人框架（如 **AstrBot**，支持 QQ/Telegram/企微/飞书/钉钉/Slack/Discord/LINE）**官方不支持闲鱼/淘宝**，用作闲鱼客服需自行开发对接层。

**信源：**
- https://github.com/cv-cat/XianYuApis
- https://github.com/AstrBotDevs/AstrBot

### 1.3 落地建议
- 直接用 **XianyuAutoAgent 或 xianyu-auto-reply** 二开，LLM 换成通义千问/Claude/本地模型 + RAG 知识库（喂入商品 FAQ、退换货政策）
- **自动发货目前主要覆盖虚拟商品/卡券**；实物商品的"1688/拼多多→闲鱼一件代发"端到端自动下单，目前**没有成熟的开源闭环，仍需人工介入采购环节**

---

## 二、模块二：1688 / 拼多多自动选品（爆品挖掘）

| 方案 | 类型 | 能力 | 验证 |
|---|---|---|---|
| **妙手 ERP** | 商业 SaaS | AI 选品、TikTok 热销选品、海外榜单同款、蓝海商品识别；原生支持 **1688 搜同款 / 批量采购 / 寻源通插件 / 一键铺货** | 3-0 ✓ |
| **万邦 Onebound 聚合 API** | 数据 API | 覆盖 25+ 平台。1688：商品详情/关键词搜索/**按图搜索**；拼多多：按 ID 取详情/关键词取列表/**搜索词统计**；显式提供"**选品中心**"与"数据块统计下载" | 3-0 ✓ |

**信源：**
- https://erp.91miaoshou.com/help_center/group_article_400.html
- https://open.onebound.cn/

### 关键提醒
- **拼多多官方没有开放的 POP 商品搜索/采集 API**，只能走万邦这类第三方聚合接口或爬虫 → 数据稳定性、合规性、IP/账号封禁风险需自行承担
- 妙手 ERP 选品强项偏**跨境**（TikTok/Temu/Shopee），纯国内 1688/拼多多选品深度需进一步验证
- **选品工作流建议**：Onebound 搜索词统计 + 按图搜索 → 拉销量/价格/评价数据 → 喂给 LLM 做"爆品打分 + 利润测算 + 蓝海判断" → 输出每日选品清单

---

## 三、模块三：小红书/抖音自动发帖 + AI 配图

| 项目 | 能力 | 验证 |
|---|---|---|
| **social-auto-upload** | 一套代码自动上传到**抖音/B站/小红书/快手/视频号/百家号/TikTok/YouTube 共 8 平台**；浏览器自动化（patchright 驱动 + 无头/隐身规避检测）| 3-0 ✓ |
| **Auto-Redbook-Skills**（MIT，Claude Code 插件）| 自动撰写笔记 → AI 生成图片卡片 → 自动发布全链路 | 2-1 ✓ |
| **XHS_ALL_IN_ONE** | 全自动流水线：**搜索热门笔记 → AI 改写标题+正文 → 上传图片 → Creator API 自动发布**；逆向签名算法，FastAPI+TS+Docker | 3-0 ✓ |
| **XiaohongshuSkills** | 基于 Chrome DevTools Protocol(CDP) 自动填标题/正文、上传图文发布 | 3-0 ✓ |

**信源：**
- https://github.com/dreammis/social-auto-upload
- https://github.com/comeonzhj/Auto-Redbook-Skills
- https://github.com/cv-cat/XHS_ALL_IN_ONE
- https://github.com/white0dew/XiaohongshuSkills

### 3.1 AI 自动配图：主流方案不是文生图大模型（反直觉但重要）

> 小红书/抖音图文的"自动配图"主流落地方式，**不是 Midjourney/SD 文生图，而是把 Markdown 内容用 HTML/CSS 模板渲染、再用 Playwright 截图成图片卡片**。

以 **Auto-Redbook-Skills** 为例：
- Markdown → HTML/CSS → Playwright 截图为 **1080×1440（3:4，小红书标准比例）** 卡片
- **8 套主题皮肤**：default / Playful Geometric / Neo-Brutalism / Botanical / Professional / Retro / Terminal / Sketch
- **4 种分页模式**：手动分隔 separator / auto-fit / auto-split / dynamic
- 发布走 `xhs` 客户端，支持**定时发布 + 可见性控制（默认仅自己可见，便于人工复核后再公开）**
- XHS_ALL_IN_ONE 另提供 AI 图片润色能力

**为什么这样做**：商品推荐帖需要"信息排版清晰、文字可控、风格统一"，模板渲染比文生图更可控、更稳定、更省成本。若坚持"真·文生图"商品配图（即梦/通义万相/SD），目前**缺乏与商品真实主图、合规要求结合的成熟自动化方案**，建议作为锦上添花，而非主力。

---

## 四、推荐架构（把三块串起来）

```
[选品层]  Onebound API/妙手 → 拉 1688/PDD 数据 → LLM 爆品打分 → 每日选品清单（人工确认）
    │
    ├──→ [上架层]  选定商品 → 闲鱼发布（半自动）
    │
[客服层]  XianyuAutoAgent + XianYuApis + 通义千问/Claude + RAG(商品FAQ)
          → 拟人化回复 + 阶梯议价 + 付款后自动发货(虚拟品) / 提醒人工(实物)
    │
[推广层]  每日选品 → LLM 写小红书/抖音文案 → HTML/CSS模板渲染配图(Playwright)
          → social-auto-upload 定时发布(默认私密→人工复核→公开)
```

**统一调度**：用一个 LLM Agent 编排层（LangChain/自研）+ 定时任务（cron）把"每日选品→文案生成→配图→发布"串成流水线；客服模块独立常驻。

---

## 五、合规与封号风险（务必逐条看）

1. **接入全为非官方**：闲鱼逆向 WebSocket 私信（XianYuApis）、小红书逆向签名（XHS_ALL_IN_ONE 的 apis/）/CDP、抖音浏览器自动化（Playwright/patchright）——平台更新协议或风控即失效或封号，隐身只是缓解
2. **许可证限制**：XianYuAssistant"请勿商用"；xianyu-auto-reply 是 AGPL-3.0（商用闭源受限）；XianyuAutoAgent 是 GPL-3.0
3. **降低封号概率的实务做法**：单账号低频、模拟真人作息、关键动作（发货/公开发帖）人工二次确认、独立设备指纹+IP、新账号先养号
4. **时效性**：逆向类项目的维护活跃度直接决定可用性，落地前务必看项目最近 commit 是否还在跟进平台更新

---

## 六、尚未解决/需定夺的问题（Open Questions）

1. **拼多多无官方选品 API**——是否接受第三方聚合接口的合规与封号风险？是否有更稳妥的官方授权数据源？
2. **实物商品自动发货未打通**——1688/PDD→闲鱼一件代发的自动下单采购环节，目前仍需人工，能否接受半自动？
3. **各开源项目长期存活率未知**——面对 2026 年 6 月后闲鱼/小红书最新风控的封号概率缺乏量化数据
4. **真·文生图配图缺成熟商品方案**——用模板渲染（推荐、稳）还是坚持文生图（炫但不稳）？

---

## 七、被否决的声明（供参考）

- "xianyu-auto-reply 集成了具名大模型供应商" —— 证据不足（投票 1-2 否决），其 README 未明确列出具体大模型供应商

---

## 八、完整信源清单

### Primary（一手主源，高可信）
- https://github.com/shaxiu/XianyuAutoAgent
- https://github.com/cv-cat/XianYuApis
- https://github.com/zhinianboke/xianyu-auto-reply
- https://github.com/IAMLZY2018/XianYuAssistant
- https://github.com/laozuzhen/xianyu-openclaw-channel
- https://github.com/AstrBotDevs/AstrBot
- https://erp.91miaoshou.com/help_center/group_article_400.html
- https://open.onebound.cn/
- https://github.com/dreammis/social-auto-upload
- https://github.com/comeonzhj/Auto-Redbook-Skills
- https://github.com/cv-cat/XHS_ALL_IN_ONE
- https://github.com/white0dew/XiaohongshuSkills
- https://www.alibabacloud.com/help/zh/model-studio/single-agent-application

### Secondary / Blog（二手，参考）
- https://news.qq.com/rain/a/20250613A01VU000 （平台自动化封号风险）
- https://www.everbrightlaw.com/CN/07/4b3df8779a975b22.aspx （合规法律视角）
- https://www.cnblogs.com/vipstone/p/19331338 （实现博客）

### Unreliable（抓取失败/无有效声明，仅留档）
- https://open.1688.com/ （官方文档需登录）
- https://open.pinduoduo.com/application/document/api （官方文档需登录）

---

## 九、下一步可选方向

- **(A) 二次开发可行性评估**：拉取 XianyuAutoAgent / xianyu-auto-reply 源码，做一份"接通义千问的改造清单"
- **(B) MVP 落地路线图**：先做哪个模块、半自动到全自动的演进路径
- **(C) Demo 脚本**：针对某一模块（选品/自动配图）写一个能跑的 Demo
