# 商品快照 JSONL 接口规范

## 文件规则

- UTF-8 编码，一行一个商品快照。
- 空行跳过；单行最大 256KB。
- `item_id`、`title`、`updated_at`、`source_url` 必填。
- 单行失败只拒绝当前商品，并写入错误报告。

## 字段

| 字段 | 类型 | 要求 |
|---|---|---|
| `item_id` | string | 1-64，字母/数字/`-`/`_` |
| `title` | string | 1-200，不能只有标点 |
| `description` | string | 可选，最多 5000 |
| `category` | string | 可选，最多 100 |
| `condition` | string | 可选，最多 100 |
| `specifications` | object | 标量或标量数组，最多两层；兼容旧字段 `specs` |
| `included_items` | array | 可选，最多 100 项，每项最多 200 字符 |
| `inventory` | object | `status` 为 `in_stock/out_of_stock/unknown`，数量为非负整数 |
| `pricing` | object | `sale_price >= 0`，金额使用 Decimal，货币为三位代码；兼容旧字段 `price` |
| `shipping` | object | 发货时效 0-720 小时，运费非负；明确包邮时 `free_shipping=true` |
| `after_sale` | string | 可选，最多 2000 |
| `faq` | array | 最多 100 条，问题 2-200，答案 1-1000 |
| `source_url` | string | `http/https`，最多 2048 |
| `updated_at` | string | 带时区 ISO-8601，未来超过 10 分钟拒绝 |

## 示例

```json
{"item_id":"A1","title":"手机支架","category":"手机配件","specifications":{"夹持桌厚":"1-6cm"},"included_items":["支架","说明书"],"inventory":{"status":"in_stock","quantity":8},"pricing":{"sale_price":39,"currency":"CNY"},"faq":[{"question":"能夹多厚？","answer":"支持1-6cm"}],"source_url":"https://example.com/A1","updated_at":"2026-08-06T12:00:00+08:00"}
```

## 错误示例

```json
{"item_id":"A 1","title":"商品","source_url":"file:///tmp/a","updated_at":"2026-08-06T12:00:00"}
```

该记录同时违反 `item_id`、`source_url` 和 `updated_at` 规则，不入库。

## 版本兼容

新增可选字段向后兼容；修改字段语义或必填规则时提升接口版本。未知字段默认忽略但写入 warning。`floor_price` 不属于该接口，继续由卖家私有议价配置管理。
