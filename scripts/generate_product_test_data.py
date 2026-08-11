"""生成商品 RAG 的完整合成快照和离线评测集。

测试资料与真实商品资料严格分开：所有 item_id 使用 TEST- 前缀，来源 URL 指向
test.example.com。它们只用于验证导入、切片、检索与回答策略，不能导入生产知识库。
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any


_PRODUCT_TYPES = (
    ("手机配件", "可调节手机支架", "铝合金", "桌面夹持 1-6cm", "黑色", "支架、说明书、收纳袋"),
    ("家居用品", "折叠收纳箱", "PP 塑料", "容量 45L", "米白色", "收纳箱、分隔板、说明书"),
    ("厨房用品", "不锈钢保温杯", "304 不锈钢", "容量 500ml", "深灰色", "保温杯、杯刷、说明书"),
    ("数码配件", "蓝牙无线耳机", "ABS", "续航 24 小时", "白色", "耳机、充电仓、数据线、说明书"),
    ("运动户外", "轻量运动水壶", "Tritan", "容量 750ml", "蓝色", "水壶、提绳、说明书"),
    ("办公文具", "可调节笔记本支架", "铝合金", "适用 11-17 英寸", "银色", "支架、防滑垫、说明书"),
    ("宠物用品", "宠物互动玩具", "环保硅胶", "直径 6cm", "橙色", "玩具、替换绳、说明书"),
    ("车载用品", "磁吸车载支架", "合金", "适用 4.7-7 英寸", "黑色", "支架、出风口夹、引磁片"),
    ("美妆工具", "旅行化妆刷套装", "人造纤维", "12 支套装", "粉色", "化妆刷、收纳包、清洁说明"),
    ("生活电器", "便携小夜灯", "ABS", "续航 8 小时", "暖白色", "小夜灯、充电线、说明书"),
)


def generate_snapshots(count: int = 40, updated_at: str | None = None) -> list[dict[str, Any]]:
    """返回覆盖商品主要字段的合成快照，不写入文件或数据库。"""
    if count < 1:
        raise ValueError("count 必须大于 0")
    timestamp = updated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    rows: list[dict[str, Any]] = []
    for position in range(count):
        category, name, material, primary_spec, color, included = _PRODUCT_TYPES[position % len(_PRODUCT_TYPES)]
        variant = position // len(_PRODUCT_TYPES) + 1
        item_id = f"TEST-{position + 1:03d}"
        price = Decimal("29.90") + Decimal(position * 7)
        quantity = 3 + position % 9
        title = f"{name} 测试款 {variant}"
        specifications = {
            "测试型号": f"{category[:2].upper()}-{variant:02d}",
            "材质": material,
            "核心参数": primary_spec,
            "颜色": color,
        }
        included_items = included.split("、")
        inventory = {"status": "in_stock", "quantity": quantity, "note": f"合成测试库存 {quantity} 件"}
        pricing = {"sale_price": str(price), "currency": "CNY"}
        shipping = {
            "dispatch_sla_hours": 24,
            "carrier": "测试快递",
            "fee": "0",
            "free_shipping": True,
            "note": "合成测试订单仅用于离线验证。",
        }
        row = {
            "item_id": item_id,
            "title": title,
            "description": f"这是 {title} 的合成测试资料，仅用于商品 RAG 验证，不能作为真实交易承诺。",
            "category": category,
            "condition": "全新测试样品",
            "specifications": specifications,
            "included_items": included_items,
            "inventory": inventory,
            "pricing": pricing,
            "shipping": shipping,
            "after_sale": "合成测试商品不产生真实订单；离线验证时模拟签收后 48 小时内反馈问题。",
            "source_url": f"https://test.example.com/products/{item_id}",
            "updated_at": timestamp,
        }
        row["faq"] = _faq(row)
        rows.append(row)
    return rows


def generate_eval_cases(snapshots: list[dict[str, Any]], questions_per_item: int = 10) -> list[dict[str, Any]]:
    """将每条快照的 FAQ 转为评测契约，覆盖规格、动态字段和售后。"""
    if questions_per_item != 10:
        raise ValueError("当前评测契约固定每商品 10 条问法")
    if not snapshots:
        return []
    cases: list[dict[str, Any]] = []
    for index, snapshot in enumerate(snapshots):
        for faq_index, faq in enumerate(snapshot["faq"]):
            expected_kind, intent = _EVAL_KINDS[faq_index]
            cases.append({
                "case_id": f"{snapshot['item_id']}-Q{faq_index + 1:02d}",
                "item_id": snapshot["item_id"],
                "query": faq["question"],
                "intent": intent,
                "expected_kind": expected_kind,
                "expected_action": "answer",
                "hard_negative_item_id": snapshots[(index + 1) % len(snapshots)]["item_id"] if faq_index == 2 else None,
                "synthetic": True,
            })
    return cases


def write_jsonl(path: str | Path, rows: list[dict[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )


def _faq(snapshot: dict[str, Any]) -> list[dict[str, str]]:
    specs = snapshot["specifications"]
    inventory = snapshot["inventory"]
    pricing = snapshot["pricing"]
    shipping = snapshot["shipping"]
    return [
        {"question": "这是什么商品？", "answer": f"这是{snapshot['title']}，仅用于 RAG 离线测试。"},
        {"question": "商品成色怎么样？", "answer": f"资料标注为{snapshot['condition']}。"},
        {"question": "核心规格和材质是什么？", "answer": f"核心参数为{specs['核心参数']}，材质为{specs['材质']}。"},
        {"question": "有哪些颜色可选？", "answer": f"测试资料标注颜色为{specs['颜色']}。"},
        {"question": "包装里有什么？", "answer": f"包含{'、'.join(snapshot['included_items'])}。"},
        {"question": "现在还有库存吗？", "answer": f"当前合成库存为{inventory['quantity']}件。"},
        {"question": "现在卖多少钱？", "answer": f"当前合成售价为{pricing['sale_price']}元。"},
        {"question": "包邮吗，多久发货？", "answer": f"测试资料为包邮，{shipping['dispatch_sla_hours']}小时内发货。"},
        {"question": "支持售后吗？", "answer": snapshot["after_sale"]},
        {"question": "这是真实在售商品吗？", "answer": "不是，这是合成测试商品，不能用于真实交易。"},
    ]


_EVAL_KINDS = (
    ("basic_info", "product_qa"),
    ("basic_info", "product_qa"),
    ("specification", "product_qa"),
    ("specification", "product_qa"),
    ("basic_info", "product_qa"),
    ("commercial", "inventory"),
    ("commercial", "price"),
    ("shipping", "logistics"),
    ("after_sale", "aftersale"),
    ("basic_info", "other"),
)


def main() -> int:
    parser = argparse.ArgumentParser(description="生成商品 RAG 合成测试数据")
    parser.add_argument("--count", type=int, default=40)
    parser.add_argument("--snapshots", default="data/product_snapshots.test.jsonl")
    parser.add_argument("--eval", dest="eval_path", default="data/product_rag_eval.test.jsonl")
    parser.add_argument("--updated-at", help="固定快照时间，便于稳定复现测试数据")
    args = parser.parse_args()

    snapshots = generate_snapshots(count=args.count, updated_at=args.updated_at)
    cases = generate_eval_cases(snapshots)
    write_jsonl(args.snapshots, snapshots)
    write_jsonl(args.eval_path, cases)
    print(json.dumps({"snapshots": len(snapshots), "eval_cases": len(cases), "synthetic": True}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
