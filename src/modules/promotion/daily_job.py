"""每日推广任务：消费已审核选品，生成待审核的双渠道内容。"""
from __future__ import annotations

import dataclasses
import datetime
from pathlib import Path
from typing import Callable

from ...config import config
from ...llm.factory import build_llm
from ...llm.base import LLMClient
from ..sourcing.store import DailyPick, SourcingPickStore
from .card_renderer import render_cards
from .copywriter import write_post
from .store import PromotionStore
from .wechat_renderer import build_wechat_article
from .xhs_exporter import export_package


def _snapshot(pick: DailyPick) -> dict:
    return {
        "pick_id": pick.id, "item_id": pick.item_id, "title": pick.title,
        "price": pick.resale_local, "currency": pick.currency, "category": pick.keyword,
        "selling_points": pick.selling_points, "image_path": pick.pic_url,
        "source_url": pick.detail_url, "reason": pick.reason, "score": pick.score,
    }


def run_daily_promotion(
    sourcing_store: SourcingPickStore,
    promotion_store: PromotionStore,
    llm: LLMClient | None = None,
    run_date: str | None = None,
    source_date: str | None = None,
    output_root: str | None = None,
    renderer: Callable = render_cards,
) -> dict:
    """每天从前一天国内已审核选品中挑最高分商品，生成一条待审核内容。"""
    today = datetime.date.fromisoformat(run_date) if run_date else datetime.date.today()
    content_date = today.isoformat()
    source_date = source_date or (today - datetime.timedelta(days=1)).isoformat()
    picks = sourcing_store.list_picks(status="approved", group="domestic", run_date=source_date)
    if not picks:
        return {"saved": 0, "reason": "no_approved_pick"}
    pick = picks[0]
    snapshot = _snapshot(pick)
    from ..sourcing.agent import to_promo_product_from_snapshot

    product = to_promo_product_from_snapshot(snapshot)
    post = write_post(product, llm or build_llm())
    # 第一张卡作为微信封面；同步微信时才会上传到平台。
    article = build_wechat_article(post, [])
    content, created = promotion_store.create(
        content_date, pick.id, snapshot, dataclasses.asdict(post), dataclasses.asdict(article),
    )
    if not created and content.status != "failed":
        return {"saved": 0, "content_id": content.id, "reason": "duplicate"}
    if not created:
        promotion_store.reset_failed(content.id)
    out = Path(output_root or Path(config.PROJECT_ROOT) / "data" / "promotion") / content_date / str(content.id)
    try:
        image_paths = renderer(post, str(out), image_path=product.image_path)
        article = build_wechat_article(post, image_paths)
        # 保存带本地图片路径的草稿描述，审批后可直接同步微信。
        promotion_store.replace_wechat_article(content.id, dataclasses.asdict(article))
        export_package(post, image_paths, str(out), snapshot)
        promotion_store.set_assets(content.id, str(out))
    except Exception as exc:  # noqa: BLE001
        promotion_store.mark_failed(content.id, str(exc))
        raise
    return {"saved": 1, "content_id": content.id, "source_date": source_date, "xhs_package_dir": str(out)}
