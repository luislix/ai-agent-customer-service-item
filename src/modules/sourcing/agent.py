"""选品 Agent：编排「搜索货源 -> 定价打分 -> 输出选品决策」，并桥接到推广模块。

selling_points 由本模块从标题/数据粗提，真正的种草文案仍交给 promotion.copywriter
（用 LLM 润色）。这样选品只产「事实卖点」，文案润色不在这里耦合 LLM。
"""
from __future__ import annotations

from ...config import config
from ..promotion.types import Product
from .factory import make_sourcing_client
from .platforms import DEFAULT_DOMESTIC, DEFAULT_OVERSEAS, PlatformPick, select_platforms
from .selector import select
from .types import SourcedPick, SourcingQuery


class SourcingAgent:
    """选品主入口。client 缺省按 SOURCING_PROVIDER 选数据源（无 key/token 自动走离线样例）。

    统一渠道框架：find_platforms() 对任意渠道（国内/跨境）测算利润、推荐最优渠道；
    find_overseas()/find_domestic() 是它的便捷封装；find() 为国内快速单价估算（兼容旧用法）。
    """

    def __init__(self, client=None):
        self.client = client or make_sourcing_client()

    def _search(self, keyword, platform, min_price, max_price, min_sales):
        return self.client.search(SourcingQuery(
            keyword=keyword, platform=platform, min_price=min_price,
            max_price=max_price, min_sales=min_sales,
        ))

    def find(
        self,
        keyword: str,
        platform: str = "1688",
        min_price: float = 0.0,
        max_price: float = 0.0,
        min_sales: int = 0,
        markup: float = 0.6,
        min_profit: float = 10.0,
        top_k: int = 5,
    ) -> list[SourcedPick]:
        """【国内快速估算】搜一个关键词，按简单加成定价返回 top_k 选品（兼容旧用法）。"""
        query = SourcingQuery(
            keyword=keyword, platform=platform, min_price=min_price,
            max_price=max_price, min_sales=min_sales,
        )
        items = self.client.search(query)
        return select(items, query, markup=markup, min_profit=min_profit, top_k=top_k)

    def find_platforms(
        self,
        keyword: str,
        markets: list[str] | None = None,
        platform: str = "1688",
        min_price: float = 0.0,
        max_price: float = 0.0,
        min_sales: int = 0,
        top_k: int = 5,
    ) -> list[PlatformPick]:
        """【统一渠道】对指定渠道分别测算利润，返回 top_k 选品（含推荐渠道与各渠道对比）。

        markets 为渠道 key 列表（如 tiktok_us/aliexpress/xianyu/pdd）；缺省走跨境默认。
        """
        items = self._search(keyword, platform, min_price, max_price, min_sales)
        return select_platforms(items, markets=markets, top_k=top_k)

    def find_overseas(self, keyword: str, platforms: list[str] | None = None, **kw) -> list[PlatformPick]:
        """【跨境】find_platforms 的便捷封装，缺省读 config.OVERSEAS_PLATFORMS。"""
        markets = platforms or _csv(config.OVERSEAS_PLATFORMS) or DEFAULT_OVERSEAS
        return self.find_platforms(keyword, markets=markets, **kw)

    def find_domestic(self, keyword: str, platforms: list[str] | None = None, **kw) -> list[PlatformPick]:
        """【国内】find_platforms 的便捷封装，缺省 闲鱼/拼多多/抖音小店。"""
        return self.find_platforms(keyword, markets=platforms or DEFAULT_DOMESTIC, **kw)


def _csv(s: str | None) -> list[str]:
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def _extract_points(pick) -> list[str]:
    """从标题/数据粗提 2-3 个事实卖点（不编造，文案润色交给 copywriter）。
    兼容 SourcedPick 与 PlatformPick（都含 .item）。"""
    points: list[str] = []
    if pick.item.sales >= 500:
        points.append(f"已售{pick.item.sales}+ 热销验证")
    # 标题里常见的卖点词
    title = pick.item.title
    for kw in ("包邮", "现货", "全配件", "礼盒", "升级", "高品质", "厂家直供", "速发"):
        if kw in title and kw not in "".join(points):
            points.append(kw)
        if len(points) >= 3:
            break
    if not points:
        points.append("品质好物")
    return points[:3]


def to_promo_product(pick, category: str = "好物") -> Product:
    """桥接：把一条选品决策转成推广模块的 Product（用建议转售价作为售价）。
    兼容 SourcedPick（.resale_price）与统一框架 PlatformPick（.best.resale_rmb）。"""
    item = pick.item
    # 售价：SourcedPick 用 resale_price；PlatformPick 用推荐渠道售价(RMB)
    price = getattr(pick, "resale_price", None)
    if price is None:
        price = pick.best.resale_rmb
    # 标题去掉进货侧的「批发/直供/走量」等不适合 C 端种草的词
    title = item.title
    for noise in ("厂家直供", "批发", "走量", "现货批发"):
        title = title.replace(noise, "")
    return Product(
        title=title.strip(),
        price=price,
        category=category,
        selling_points=_extract_points(pick),
        image_path=item.pic_url if item.pic_url.startswith("http") else "",
    )


def to_promo_product_from_snapshot(snapshot: dict) -> Product:
    """推广只读取审核时写入的事实快照，不临时依赖选品列表或供应商接口。"""
    title = str(snapshot["title"])
    for noise in ("厂家直供", "批发", "走量", "现货批发"):
        title = title.replace(noise, "")
    return Product(
        title=title.strip(),
        price=float(snapshot["price"]),
        category=str(snapshot.get("category") or "每日好物"),
        selling_points=[str(value) for value in snapshot.get("selling_points", [])],
        image_path=str(snapshot.get("image_path") or ""),
    )
