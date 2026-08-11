"""文案生成：用 LLM 把一个商品写成小红书种草帖（封面+内容卡所需字段 + 发布正文）。

无 LLM key 时退化为模板文案，保证流水线可跑。
"""
from __future__ import annotations

import json

from ...llm.base import ChatMessage, LLMClient
from .types import Product, PromoPost

_SYS = (
    "你是资深小红书种草博主，专写二手好物推荐。语言年轻、真诚、有网感，"
    "适当用 emoji，不浮夸不虚假。严格输出 JSON，不要多余文字。"
)

_SCHEMA_HINT = """请基于商品信息，输出如下 JSON（中文）：
{
  "kicker": "品类标签(4-6字,如 数码好物/居家神器)",
  "title": "封面大标题(12-18字,口语种草感,用 **关键词** 包裹1-2个最想突出的词)",
  "subtitle": "副标题一句话(15-25字)",
  "cover_points": ["短卖点1(≤10字)","短卖点2","短卖点3"],
  "content_eyebrow": "内容卡小标(如 为什么推荐它)",
  "content_heading": "内容卡标题(10-16字,用 **词** 高亮)",
  "content_items": [
     {"lead":"小标题(≤10字)","desc":"一句说明(20-35字)"},
     {"lead":"...","desc":"..."},
     {"lead":"...","desc":"..."}
  ],
  "callout": "结尾提示(20-35字,用 **词** 加粗,可含价格/行动号召)",
  "xhs_caption": "完整小红书正文(含标题、3-5行正文带emoji、结尾5-8个#话题标签)"
}"""


_SYS_EN = (
    "You are a top TikTok Shop creator writing punchy product promos for US/UK shoppers. "
    "Tone: young, authentic, hook-first, light emoji, no hype lies. "
    "Output strict JSON only, no extra text."
)

_SCHEMA_HINT_EN = """Based on the product, output this JSON (English):
{
  "kicker": "category tag (1-3 words, e.g. Tech Gadget/Home Hack)",
  "title": "cover headline (6-10 words, scroll-stopping, wrap 1-2 key words in **)",
  "subtitle": "one-line subhead (8-14 words)",
  "cover_points": ["short selling point1 (<=5 words)","point2","point3"],
  "content_eyebrow": "small label (e.g. Why you'll love it)",
  "content_heading": "content card title (6-10 words, wrap key word in **)",
  "content_items": [
     {"lead":"mini title (<=5 words)","desc":"one line (10-18 words)"},
     {"lead":"...","desc":"..."},
     {"lead":"...","desc":"..."}
  ],
  "callout": "closing line (10-18 words, wrap key word in **, may include price/CTA)",
  "xhs_caption": "full TikTok caption (hook line + 2-4 short lines with emoji + 5-8 #hashtags)"
}"""


def _fallback_en(p: Product, index: str) -> PromoPost:
    """无 LLM 时的英文模板文案。"""
    pts = p.selling_points[:3] or ["Premium quality", "Great price", "Fast shipping"]
    return PromoPost(
        kicker=p.category, index=index,
        title=f"This **{p.title[:14]}** is a game changer",
        subtitle="Viral find that's actually worth it 🔥",
        price=f"{p.price:g}", cover_points=pts,
        content_eyebrow="Why you'll love it",
        content_heading=f"Why **{p.title[:10]}** is worth it",
        content_items=[{"lead": s, "desc": "Tested and it just works — solid for daily use."} for s in pts],
        callout=f"Get yours for **{p.price:g}** — limited stock, grab it fast!",
        handle="Daily Finds Shop", footer_note="Follow for more deals ❤",
        xhs_caption=(f"You NEED this {p.title}! 😍\n\n"
                     + "".join(f"✅{s}\n" for s in pts)
                     + "\n#tiktokmademebuyit #amazonfinds #musthaves #gadgets #dealsoftheday"),
    )


def _fallback(p: Product, index: str) -> PromoPost:
    """无 LLM 时的模板文案，保证流水线可跑。"""
    pts = p.selling_points[:3] or ["品质保证", "价格美丽", "现货速发"]
    return PromoPost(
        kicker=p.category, index=index,
        title=f"这个 **{p.title[:8]}** 也太香了吧",
        subtitle="捡漏二手好物，钱包和需求都照顾到了～",
        price=f"{p.price:g}", cover_points=pts,
        content_eyebrow="为什么推荐它",
        content_heading=f"**{p.title[:6]}** 凭什么值得入",
        content_items=[{"lead": s, "desc": "实测好用，细节到位，日常完全够。"} for s in pts],
        callout=f"到手价 **¥{p.price:g}**，喜欢的冲，库存有限～",
        xhs_caption=(f"{p.title} 真的可以闭眼入！\n\n💰到手价 ¥{p.price:g}\n"
                     + "".join(f"✅{s}\n" for s in pts)
                     + "\n#二手好物 #捡漏 #闲鱼好物 #好物推荐"),
    )


def write_post(product: Product, llm: LLMClient, index: str = "01", locale: str = "zh") -> PromoPost:
    """生成种草帖。locale='zh' 小红书中文（国内）/ 'en' TikTok 英文（跨境）。"""
    is_en = locale == "en"
    sys_prompt, hint, fallback = (
        (_SYS_EN, _SCHEMA_HINT_EN, _fallback_en) if is_en else (_SYS, _SCHEMA_HINT, _fallback)
    )
    if not getattr(llm, "available", True) or llm.name == "placeholder":
        return fallback(product, index)
    if is_en:
        prompt = (
            f"Product: {product.title}\nPrice: {product.price}\nCategory: {product.category}\n"
            f"Known selling points: {(', '.join(product.selling_points)) or 'none'}\n\n{hint}"
        )
    else:
        prompt = (
            f"商品标题：{product.title}\n价格：{product.price}\n品类：{product.category}\n"
            f"已知卖点：{('、'.join(product.selling_points)) or '无'}\n\n{hint}"
        )
    try:
        raw = llm.chat([ChatMessage("system", sys_prompt), ChatMessage("user", prompt)],
                       temperature=0.9)
        d = json.loads(_extract_json(raw))
        return PromoPost(
            kicker=d["kicker"], index=index, title=d["title"], subtitle=d["subtitle"],
            price=f"{product.price:g}", cover_points=d["cover_points"][:3],
            content_eyebrow=d["content_eyebrow"], content_heading=d["content_heading"],
            content_items=d["content_items"][:4], callout=d["callout"],
            xhs_caption=d.get("xhs_caption", ""),
        )
    except Exception:  # noqa: BLE001 LLM 异常/解析失败 -> 退化模板
        return fallback(product, index)


def _extract_json(text: str) -> str:
    """从 LLM 输出里抠出 JSON（容忍 ```json 包裹或前后多余文字）。"""
    t = text.strip()
    if "```" in t:
        t = t.split("```")[1]
        if t.startswith("json"):
            t = t[4:]
    s, e = t.find("{"), t.rfind("}")
    return t[s:e + 1] if s >= 0 and e > s else t
