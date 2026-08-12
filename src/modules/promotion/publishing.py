"""审批后的渠道交付服务。

微信仅创建草稿；小红书可选地自动填充创作后台，但最终公开发布仍由人工完成。
"""
from __future__ import annotations

from ...config import config
from .store import PromotionStore
from .types import WeChatArticle
from .wechat_client import WeChatClient
from .xhs_browser import XHSBrowserConfig, XHSBrowserPublisher


def sync_wechat_draft(store: PromotionStore, content_id: int,
                      client: WeChatClient | None = None) -> str | None:
    """把已批准内容写入微信草稿箱，返回 media_id；无凭证时保持待同步。"""
    content = store.get(content_id)
    if content is None:
        raise ValueError("推广内容不存在")
    if content.status != "approved":
        raise ValueError("只有已审核通过的内容可以同步微信草稿")
    delivery = store.delivery(content_id, "wechat")
    if delivery is None:
        raise RuntimeError("微信交付记录不存在")
    if delivery.status == "draft_created":
        return delivery.external_id
    client = client or WeChatClient(config.WECHAT_APP_ID or "", config.WECHAT_APP_SECRET or "")
    if not client.available:
        return None
    try:
        media_id = client.create_draft(WeChatArticle(**content.wechat_article))
    except Exception as exc:  # noqa: BLE001
        store.record_wechat_failure(content_id, str(exc))
        raise
    store.record_wechat_draft(content_id, media_id)
    return media_id


def prepare_xhs_browser(store: PromotionStore, content_id: int,
                        publisher: XHSBrowserPublisher | None = None) -> str:
    """把已审核小红书内容填入创作后台，停在人工发布前。"""
    content = store.get(content_id)
    if content is None:
        raise ValueError("推广内容不存在")
    if content.status != "approved":
        raise ValueError("只有已审核通过的内容可以打开小红书发布页")
    delivery = store.delivery(content_id, "xhs")
    if delivery is None or delivery.status not in {"package_ready", "awaiting_manual_publish", "failed"}:
        raise ValueError("小红书发布包尚未就绪")
    if not content.asset_dir:
        raise ValueError("小红书发布包目录为空")
    publisher = publisher or XHSBrowserPublisher(XHSBrowserConfig.from_env(config.PROJECT_ROOT))
    try:
        output = publisher.prepare(
            content.asset_dir,
            content.xhs_post.get("title", ""),
            content.xhs_post.get("xhs_caption", ""),
        )
    except Exception as exc:  # noqa: BLE001
        store.record_xhs_failure(content_id, str(exc))
        raise
    store.mark_xhs_awaiting_publish(content_id)
    return output
