# 独立商品采集模块

本目录是当前项目的外部商品数据生产者。它只输出阶段一商品快照 JSONL，不访问当前项目的 RAG、数据库、Embedding 或自动发布流程。

## 数据源边界

默认支持两种 Provider：

- `--fixture`：离线回归，不访问网络；
- `--api-base-url`：符合本目录 `HttpJsonProvider` 约定的授权 API。

真实授权 API 字段不同，请新增适配器实现 `SearchProvider`/`DetailProvider`，不要在此处逆向或绕过平台访问控制。认证失败会停止任务，不会自动切换到其他数据源。

## 离线运行

```bash
PYTHONPATH=src python -m xianyu_product_crawler \
  --keyword-file keywords.txt \
  --fixture fixtures/provider.json \
  --per-keyword-limit 20 \
  --total-limit 50 \
  --delay 0 \
  --output out/product_snapshots.jsonl \
  --markdown out/review.md \
  --errors out/errors.jsonl \
  --raw-dir out/raw
```

人工审核通过后，再回到仓库根目录运行：

```bash
python -m scripts.ingest_product_snapshots \
  xianyu_product_crawler/out/product_snapshots.jsonl \
  --errors xianyu_product_crawler/out/import.errors.jsonl \
  --preview xianyu_product_crawler/out/chunks.preview.jsonl
```

原始响应默认只保存脱敏副本；使用 `--no-raw` 可关闭保存。页面未明确提供的商品事实保持为空，不由模型补全。

## 终端关键词自动采集（Chrome 扩展）

在 Chrome 已登录闲鱼、扩展已加载且扩展设置中的本机接收地址和令牌已配置后，直接运行：

```bash
cd xianyu_product_crawler
PYTHONPATH=src python -m xianyu_product_crawler browser
```

首次运行会在终端打印“本机采集令牌”；将它填入扩展弹窗的令牌输入框，接收地址保持 `http://127.0.0.1:8765/captures`。修改或重新加载扩展后，先在 `chrome://extensions` 点击扩展的“重新加载”，再启动终端任务。

终端提示 `请输入关键词：` 后输入一个关键词（例如 `手机支架`）。扩展会自动打开搜索页、读取商品详情链接、逐个打开详情页并提交当前页面可见资料；不再需要手动点击“采集当前商品”。

每次任务独立写入 `out/keyword-runs/<task_id>/`：

- `product_snapshots.jsonl`：阶段一商品快照；
- `review.md`：人工审阅报告；
- `errors.jsonl`：搜索、页面或字段提取失败；
- `task.json`：任务关键词、状态和采集计数；
- `raw/`：脱敏原始详情。

默认最多采集 20 个商品，每个详情页间隔 2 秒。可用 `--max-items`、`--delay` 和 `--search-url-template` 调整。登录失效、验证码或安全验证会停止任务，不尝试绕过。

该命令会启动绑定 `127.0.0.1` 的本机控制/接收服务；不要同时运行独立的 `receiver` 占用同一个端口。

多个关键词任务完成后，在仓库根目录合并并去重：

```bash
python scripts/merge_keyword_snapshot_runs.py \
  --run-root xianyu_product_crawler/out/keyword-runs \
  --output xianyu_product_crawler/out/keyword-dataset.jsonl \
  --report xianyu_product_crawler/out/keyword-dataset.merge-report.json \
  --review xianyu_product_crawler/out/keyword-dataset.review.md
```

旧任务没有 `task.json` 时，可补充映射，例如：

```bash
python scripts/merge_keyword_snapshot_runs.py \
  --legacy-keyword 072ca502eeb7=手机支架
```

合并只读取和生成待审核文件，不会导入 RAG。

## 手动选品自动采集

此模式不做自动搜索、自动翻页、登录或验证码处理。你手动在闲鱼打开商品详情页后，由浏览器扩展采集当前可见资料到本机。

1. 启动本机接收服务：

```bash
cd xianyu_product_crawler
PYTHONPATH=src python -m xianyu_product_crawler.receiver --output-dir out/captures
```

终端会打印本机采集令牌。该服务只监听 `127.0.0.1`，首次生成的令牌会保存在 `out/captures/.collector-token`，不要提交到版本库。

2. 在 Chrome 或 Edge 打开扩展管理页，开启开发者模式，点击“加载已解压的扩展程序”，选择 `xianyu_product_crawler/extension/`。

3. 打开扩展，在“本机采集令牌”填入终端打印的令牌。然后手动打开一个闲鱼商品详情页，点击浏览器工具栏的“采集当前商品”，或页面右下角的同名按钮。

4. 采集完成后构建待审核快照：

```bash
cd xianyu_product_crawler
PYTHONPATH=src python -m xianyu_product_crawler.build_dataset \
  --capture-dir out/captures/inbox \
  --output out/product_snapshots.jsonl \
  --markdown out/review.md \
  --errors out/errors.jsonl
```

同一个商品重复点击采集会更新原来的 `item_<item_id>.json`，不会新增重复记录。

审核 `out/review.md` 后，从仓库根目录运行既有导入命令。扩展不请求或读取 Cookie；接收服务会脱敏 Cookie、Token、手机号、电话和地址字段，且拒绝非 `goofish.com` 页面。
