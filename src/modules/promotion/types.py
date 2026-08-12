"""推广模块数据结构。"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Product:
    """待种草的商品（可来自选品模块或手填）。"""
    title: str
    price: float
    category: str = "好物"
    selling_points: list[str] = field(default_factory=list)  # 已知卖点（可空，LLM 会补）
    image_path: str = ""                                     # 本地商品图（可空，用占位）


@dataclass
class PromoPost:
    """一条小红书种草帖的全部内容（文案 + 两张卡片所需字段）。

    标题/标题类字段里用 **关键词** 标记需要高亮（渲染时转成荧光/加粗）。
    """
    # 封面卡
    kicker: str                      # 品类标签，如 "数码好物"
    index: str                       # 序号，如 "01"
    title: str                       # 大标题（含 **高亮**）
    subtitle: str                    # 副标题一句话
    price: str                       # 到手价（字符串，便于带小数/区间）
    cover_points: list[str]          # 封面 3 个短卖点

    # 内容卡
    content_eyebrow: str             # 小标
    content_heading: str             # 内容卡标题（含 **高亮**）
    content_items: list[dict]        # [{lead, desc}, ...]
    callout: str                     # 结尾提示框（含 **加粗**）

    # 通用
    handle: str = "闲鱼好物铺"
    footer_note: str = "点赞收藏不迷路 ❤"

    # 发布用的小红书正文文案（标题+正文+话题标签）
    xhs_caption: str = ""


@dataclass
class WeChatArticle:
    """待写入微信服务号草稿箱的图文消息。

    ``content_html`` 可使用 ``{{image:N}}`` 占位符，微信客户端上传正文图片后
    才替换成微信公众号认可的 URL。
    """
    title: str
    digest: str
    author: str
    content_html: str
    cover_image_path: str
    inline_image_paths: list[str] = field(default_factory=list)
