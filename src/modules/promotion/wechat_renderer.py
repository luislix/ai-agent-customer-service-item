"""把推广内容渲染成微信公众号图文 HTML。"""
from __future__ import annotations

import html
import re

from .types import PromoPost, WeChatArticle


def _plain(text: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"\1", text).strip()


def build_wechat_article(post: PromoPost, image_paths: list[str]) -> WeChatArticle:
    """生成微信草稿描述，图片 URL 由微信客户端上传后填入。"""
    title = _plain(post.title)[:32]
    digest = _plain(post.subtitle)[:120]
    pieces = [f"<p>{html.escape(_plain(post.subtitle))}</p>"]
    if image_paths:
        pieces.append('<p><img src="{{image:0}}"></p>')
    for item in post.content_items:
        pieces.append(
            f"<h3>{html.escape(str(item['lead']))}</h3>"
            f"<p>{html.escape(str(item['desc']))}</p>"
        )
    pieces.append(f"<p><strong>{html.escape(_plain(post.callout))}</strong></p>")
    if len(image_paths) > 1:
        pieces.append('<p><img src="{{image:1}}"></p>')
    return WeChatArticle(
        title=title or "每日好物",
        digest=digest,
        author=post.handle,
        content_html="".join(pieces),
        cover_image_path=image_paths[0] if image_paths else "",
        inline_image_paths=image_paths,
    )
