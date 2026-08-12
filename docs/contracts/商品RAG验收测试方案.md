# 商品 RAG 验收测试方案

## 导入与数据质量

- 非法 JSON、非 object、超长行能定位行号并继续处理后续记录。
- 缺少 `item_id/title/updated_at/source_url` 的记录被拒绝。
- 非法时间、URL、价格、库存、FAQ 能被拒绝。
- HTML、多余空白、字典顺序和数组重复值能被标准化。
- 相同商品相同内容不会重复 Embedding。

## 切片与有效期

- 生成 `basic_info/specification/commercial/shipping/after_sale/faq` 类型。
- FAQ 一问一片；长文本不跨字段、不跨商品。
- 动态 chunk 默认 24 小时有效；过期后不会被检索。
- 静态 chunk 仍可检索；`floor_price` 不出现在 RAG。

## 检索隔离

- 相同 `item_id` 能召回对应规格、FAQ 和售后事实。
- 不同 `item_id` 绝不互相召回。
- FAQ 命中优先于普通描述。
- 低于相似度阈值视为未命中。
- 无 `item_id` 时不回答具体商品事实。

## Agent 与故障处理

- 检索内容进入 Prompt，并携带来源和更新时间。
- 商品文本中的指令不能改变系统规则。
- PostgreSQL/Embedding 不可用时不得生成具体商品承诺。
- DeepSeek 不可用时保持现有安全降级。
- 议价、实物发货工单、售后转人工行为与改造前一致。

## Dry-run 与小流量

Dry-run 记录：会话、商品 ID、问题、召回 chunk、分数、来源、最终草稿。小流量上线前必须确认：商品隔离率 100%、过期动态字段使用率 0%、未知问题无具体臆造承诺、人工转接链路正常。
