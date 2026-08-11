"""选品 demo + 选品->推广全链路（统一渠道框架）：

    python -m scripts.run_sourcing_demo 手机支架            # 跨境+国内两组清单
    python -m scripts.run_sourcing_demo 手机支架 --promo    # 给国内Top1生成小红书种草帖+卡片

数据源按 SOURCING_PROVIDER 选（justoneapi/onebound），无 key/token 自动走离线样例。
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:  # noqa: BLE001
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import config  # noqa: E402
from src.modules.sourcing.agent import SourcingAgent, to_promo_product  # noqa: E402
from src.modules.sourcing.platforms import select_platforms  # noqa: E402
from src.modules.sourcing.types import SourcingQuery  # noqa: E402

_GROUPS = [("跨境", ["tiktok_us", "aliexpress"]), ("国内", ["xianyu", "pdd", "douyin"])]


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    keyword = args[0] if args else "保温杯"
    do_promo = "--promo" in argv

    agent = SourcingAgent()
    avail = "真实 API" if agent.client.available else "离线样例"
    print(f"货源：{agent.client.name}（{avail}）\n选品关键词：{keyword}\n" + "=" * 60)

    items = agent.client.search(SourcingQuery(keyword=keyword, min_sales=500))
    if not items:
        print("没搜到合适货源（换关键词或放宽销量门槛）")
        return 1

    for label, markets in _GROUPS:
        print(f"【{label}】按渠道测算，推荐最优：")
        picks = select_platforms(items, markets=markets, top_k=3)
        for i, pk in enumerate(picks, 1):
            b = pk.best
            print(f"  [{i}] 分{pk.score:<5} {pk.item.title[:28]}")
            print(f"      进价¥{pk.item.cost_price:g} 已售{pk.item.sales} → ★{b.platform} "
                  f"{b.currency}{b.resale_local:g} 净利¥{b.profit:g}（{b.margin*100:.0f}%）")
        print("-" * 60)

    if do_promo:
        from src.llm.factory import build_llm
        from src.modules.promotion.card_renderer import render_cards
        from src.modules.promotion.copywriter import write_post

        overseas = "--overseas" in argv
        if overseas:
            picks = select_platforms(items, markets=["tiktok_us", "aliexpress"], top_k=1)
            locale, outsub, channel = "en", "sourcing_promo_en", "TikTok"
        else:
            picks = select_platforms(items, markets=["xianyu", "pdd", "douyin"], top_k=1)
            locale, outsub, channel = "zh", "sourcing_promo", "小红书"
        if not picks:
            print("无可推广选品")
            return 0

        pick = picks[0]
        product = to_promo_product(pick, category="好物")
        if overseas:   # 跨境用推荐渠道的本币售价
            product.price = pick.best.resale_local
        price_str = f"{pick.best.currency}{product.price:g}"
        print(f"\n→ 给 {pick.best.platform} Top1「{product.title}」({price_str}) 生成{channel}文案…")
        post = write_post(product, build_llm(), index="01", locale=locale)
        print("封面标题：", post.title)
        print("发布正文：\n" + post.xhs_caption)
        out_dir = str(Path(config.PROJECT_ROOT) / "data" / outsub)
        try:
            files = render_cards(post, out_dir, image_path=product.image_path)
            print("已生成卡片：", "、".join(files))
        except Exception as e:  # noqa: BLE001
            print(f"[渲染跳过] {e}")
    else:
        print("加 --promo 生成小红书种草卡片；再加 --overseas 生成 TikTok 英文文案。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
