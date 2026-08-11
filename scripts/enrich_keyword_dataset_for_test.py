"""Create a fact-grounded enriched dataset for local RAG testing.

The crawler intentionally does not infer facts from free-form descriptions.  This
script is an explicit test-data step: it only promotes phrases that are already
present in the captured description into structured fields and FAQ candidates.
The original JSONL is never modified.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def _text(row: dict[str, Any]) -> str:
    # The captured title is also an upstream source: many marketplace listings
    # put "全新", "包邮", colors, or the headline price only in the title.
    title = str(row.get("title") or "").strip()
    description = str(row.get("description") or "").strip()
    return re.sub(r"\s+", " ", f"{title} {description}").strip()


def _sentences(text: str) -> list[str]:
    return [part.strip(" ，,；;\n") for part in re.split(r"[。！？!；;\n]+", text) if part.strip()]


def _first_sentence(text: str, *patterns: str) -> str | None:
    for sentence in _sentences(text):
        if any(re.search(pattern, sentence, re.IGNORECASE) for pattern in patterns):
            return sentence[:1000]
    return None


def _condition(row: dict[str, Any], text: str) -> str | None:
    if row.get("condition"):
        return row["condition"]
    if re.search(r"全新未拆封|全新未使用|全新正品|全新！！！|全新包邮", text):
        return "全新未拆封" if re.search(r"未拆封", text) else "全新"
    if re.search(r"99新|9[～至-]95新|几乎全新", text):
        return "几乎全新"
    if re.search(r"闲置|没怎么用|使用不久", text):
        return "二手闲置"
    return None


def _specifications(row: dict[str, Any], text: str) -> dict[str, Any] | None:
    specs = dict(row.get("specifications") or row.get("specs") or {})

    def add(key: str, value: Any) -> None:
        if value not in (None, "", [], {}):
            specs.setdefault(key, value)

    material_terms = [
        "铝合金", "合金", "金属", "棉麻", "麂皮绒", "钢管", "不锈钢", "钛钢",
        "S925银", "925银", "陶瓷", "玻璃", "PVC", "原生海绵",
    ]
    materials = [term for term in material_terms if term.lower() in text.lower()]
    if materials:
        add("材质", materials[0] if len(materials) == 1 else materials)

    color_match = re.search(r"颜色[：:]\s*([^，,。；;]+)", text)
    if color_match:
        colors = [x.strip(" 、，,") for x in re.split(r"[/、,，]|和|及", color_match.group(1)) if x.strip()]
        colors = [x for x in colors if len(x) <= 20 and not re.search(r"(优先|默认|告诉我|可选)$", x)]
        if colors:
            add("颜色", colors if len(colors) > 1 else colors[0])

    if re.search(r"苹果安卓通用|手机和平板|手机平板|ipad|iPad", text):
        add("兼容设备", "手机和平板" if re.search(r"手机和平板|手机平板", text) else "苹果、安卓设备")
    for pattern, key in [
        (r"最高\s*([0-9.]+\s*[米m])", "最高高度"),
        (r"([0-9.]+\s*[米m])\s*(?:支架|高度)", "高度"),
        (r"收起来是\s*([0-9.]+\s*cm)", "收纳长度"),
        (r"链长(?:可调节)?[：:]?\s*([0-9.\-~～]+\s*(?:cm|厘米)?)", "链长"),
        (r"续航(?:时间)?\s*([0-9.\-~～]+\s*小时)", "续航"),
        (r"宽度[：:]?\s*([0-9.]+\s*cm)", "宽度"),
    ]:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            add(key, match.group(1).strip())

    dimension_match = re.search(
        r"(?:产品尺寸|尺寸)[：:]?\s*长\s*([0-9.]+\s*cm)\s*宽\s*([0-9.]+\s*cm)\s*高\s*([0-9.]+\s*cm)",
        text,
        re.IGNORECASE,
    )
    if dimension_match:
        add("尺寸", "长{}×宽{}×高{}".format(*[part.strip() for part in dimension_match.groups()]))

    compatibility = re.search(r"仅支持[^。；;]+", text)
    if compatibility:
        add("适配范围", compatibility.group(0).strip())
    if re.search(r"可旋转|360.?度", text):
        add("功能", "支持旋转调节")
    return specs or None


def _inventory(row: dict[str, Any], text: str) -> dict[str, Any] | None:
    if row.get("inventory"):
        return row["inventory"]
    signal = _first_sentence(text, r"现货", r"能拍就是有货", r"可直拍", r"库存不多", r"剩下", r"还剩")
    if not signal:
        return None
    return {"status": "in_stock", "quantity": None, "note": signal}


def _price(row: dict[str, Any], text: str) -> dict[str, Any] | None:
    current = row.get("pricing") or row.get("price")
    if current:
        return current
    # Only capture amounts explicitly followed by 元/块; dates and dimensions
    # therefore cannot accidentally become prices.
    values = []
    for match in re.finditer(r"(?<![\d.])([0-9]+(?:\.[0-9]+)?)\s*(?:元|块)", text):
        value = float(match.group(1))
        if value <= 100000:
            values.append(value)
    values = sorted(set(values))
    if not values:
        return None
    if len(values) == 1:
        return {"sale_price": str(values[0]).rstrip("0").rstrip("."), "currency": "CNY"}
    return {
        "min_price": str(values[0]).rstrip("0").rstrip("."),
        "max_price": str(values[-1]).rstrip("0").rstrip("."),
        "currency": "CNY",
    }


def _shipping(row: dict[str, Any], text: str) -> dict[str, Any] | None:
    current = row.get("shipping")
    if current:
        return current
    if not re.search(r"包邮|不包邮|补邮|补运费|自提|不邮寄|发货", text):
        return None
    hours = None
    if re.search(r"当天发货|当日发货", text):
        hours = 24
    else:
        match = re.search(r"(?:拍下|下单后?|一般拍下后?)\s*(\d+)\s*小时内发货", text)
        if match:
            hours = int(match.group(1))
        elif re.search(r"隔天发货", text):
            hours = 48
    note = _first_sentence(text, r"偏远.*不包邮", r"新疆.*补邮", r"自提", r"不邮寄")
    return {"dispatch_sla_hours": hours, "carrier": None, "fee": "0" if "包邮" in text else None,
            "free_shipping": "包邮" in text and not re.search(r"偏远.*不包邮|补邮|补运费", text), "note": note}


def _after_sale(row: dict[str, Any], text: str) -> str | None:
    if row.get("after_sale"):
        return row["after_sale"]
    sentences = _sentences(text)
    relevant = [s for s in sentences if re.search(r"退货|退换|不退不换|售后|质保|破损|瑕疵|运费", s)]
    if not relevant:
        return None
    return "；".join(dict.fromkeys(relevant))[:2000]


def _faq(row: dict[str, Any], *, condition: str | None, specs: dict[str, Any] | None,
         inventory: dict[str, Any] | None, pricing: dict[str, Any] | None,
         shipping: dict[str, Any] | None, after_sale: str | None, text: str) -> list[dict[str, str]]:
    if row.get("faq"):
        return row["faq"]
    faq: list[dict[str, str]] = []

    def add(question: str, answer: str | None) -> None:
        if not answer:
            return
        if question.casefold() not in {item["question"].casefold() for item in faq}:
            faq.append({"question": question, "answer": answer[:1000]})

    add("这是什么商品？", row.get("title"))
    if condition:
        add("商品成色如何？", f"商品描述标注为：{condition}。")
    if specs:
        for key, value in specs.items():
            if key in {"品牌", "型号", "材质", "颜色", "兼容设备", "适配范围", "高度", "最高高度", "尺寸", "链长", "续航", "功能"}:
                question = {
                    "品牌": "商品品牌是什么？", "型号": "商品型号是什么？", "材质": "材质是什么？",
                    "颜色": "有哪些颜色？", "兼容设备": "支持哪些设备？", "适配范围": "适配哪些型号？",
                    "高度": "高度是多少？", "最高高度": "最高高度是多少？", "尺寸": "商品尺寸是多少？",
                    "链长": "链长是多少？", "续航": "续航时间多久？", "功能": "支持哪些功能？",
                }.get(key, f"{key}是什么？")
                add(question, f"商品描述标注：{key}为{value}。")
    if inventory:
        add("现在有现货吗？", f"商品描述写明：{inventory['note'] or '当前为现货状态'}。")
    if pricing:
        if "sale_price" in pricing:
            add("现在卖多少钱？", f"当前采集到的商品价格为 {pricing['sale_price']} 元。")
        else:
            add("价格区间是多少？", f"商品描述中列出的价格区间为 {pricing['min_price']} 至 {pricing['max_price']} 元，具体套餐以下单选项为准。")
    if shipping:
        answer = "包邮。" if shipping.get("free_shipping") else "商品描述未承诺所有地区包邮，偏远地区请先确认运费。"
        if shipping.get("dispatch_sla_hours"):
            answer += f"描述中标注约 {shipping['dispatch_sla_hours']} 小时内发货。"
        add("包邮吗？多久发货？", answer)
    if after_sale:
        add("支持退换或售后吗？", after_sale)

    # Add one FAQ for an explicit compatibility restriction when it was not
    # promoted into specifications.
    restriction = re.search(r"仅支持[^。；;]+", text)
    if restriction:
        add("有哪些适配限制？", f"商品描述写明：{restriction.group(0)}。")
    return faq


def enrich_row(row: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(row)
    text = _text(row)
    condition = _condition(row, text)
    specs = _specifications(row, text)
    inventory = _inventory(row, text)
    pricing = _price(row, text)
    shipping = _shipping(row, text)
    after_sale = _after_sale(row, text)
    enriched.update({
        "condition": condition,
        "specifications": specs,
        "specs": specs,
        "inventory": inventory,
        "pricing": pricing,
        "price": pricing,
        "shipping": shipping,
        "after_sale": after_sale,
    })
    enriched["faq"] = _faq(row, condition=condition, specs=specs, inventory=inventory,
                            pricing=pricing, shipping=shipping, after_sale=after_sale, text=text)
    return enriched


def enrich_file(input_path: str | Path, output_path: str | Path) -> tuple[int, int]:
    rows = []
    for line_number, line in enumerate(Path(input_path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"第 {line_number} 行不是 object")
        rows.append(enrich_row(row))
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")
    faq_count = sum(1 for row in rows if row.get("faq"))
    return len(rows), faq_count


def main() -> int:
    parser = argparse.ArgumentParser(description="为本地 RAG 测试生成基于商品描述的补全快照")
    parser.add_argument("input", nargs="?", default="xianyu_product_crawler/out/keyword-dataset.jsonl")
    parser.add_argument("output", nargs="?", default="xianyu_product_crawler/out/keyword-dataset.enriched.jsonl")
    args = parser.parse_args()
    total, faq_count = enrich_file(args.input, args.output)
    print(f"已生成 {args.output}：{total} 条商品，{faq_count} 条包含 FAQ")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
