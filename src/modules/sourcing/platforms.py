"""统一销售渠道框架：国内 / 跨境所有平台都用一份「平台档」描述，按渠道测算利润。

设计目标（通用、可扩展）：
  - 新增一个销售渠道 = 往 PROFILES 加一份 PlatformProfile，零改算法。
  - 国内（闲鱼/拼多多/抖音/淘宝/天猫）与跨境（TikTok/速卖通）共用同一套利润模型，
    差异只体现在参数上（是否跨境、汇率、佣金、物流、加价空间）。
  - 面向「无货源 / 一件代发」：进价=代发价（不压货、无库存成本），
    单独计代发服务费(dropship_fee_rmb)与履约/物流(fulfillment_rmb)。

利润模型（统一折算到 RMB 口径）：
    目标售价(本币) = 取心理价(进价 × 加价倍率 / 汇率)        # 国内汇率=1
    目标售价(RMB)  = 目标售价(本币) × 汇率
    净利润(RMB)    = 售价 − 进价 − 售价×佣金率 − 售价×退货率
                      − 履约/物流 − 代发费 − 固定费

⚠️ 佣金率为 2025-2026 公开费率校准；物流/代发费/部分国内平台扣点为**估算值**，
   见各档 note，务必按真实店铺数据校准。汇率为快照需定期更新。
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, replace
from pathlib import Path

from ...config import config
from .selector import psych_price
from .types import SourcedItem, SourcingQuery

# 汇率快照（截至 2026-06-29，需定期更新）
FX_USD = 6.80
FX_GBP = 9.20   # 估算，调研未核实


@dataclass(frozen=True)
class PlatformProfile:
    """一个销售渠道的利润参数。国内渠道 cross_border=False、fx_to_rmb=1.0、currency='¥'。"""
    key: str
    name: str
    cross_border: bool
    currency: str            # 展示币种符号
    fx_to_rmb: float         # 1 单位本币 = 多少 RMB（国内=1.0）
    commission_rate: float   # 平台综合费率（佣金+交易/软件/支付费，打包）
    fulfillment_rmb: float   # 履约/物流成本/件（RMB）：国内快递 or 跨境头程+尾程
    dropship_fee_rmb: float  # 一件代发服务费/件（RMB）
    return_rate: float       # 退货率（按售价折损）
    sell_multiple: float     # 建议加价倍率（进价→目标售价，RMB 口径）
    fixed_fee_rmb: float = 0.0  # 每单固定费（RMB）
    note: str = ""           # 参数来源/置信度


# 销售渠道注册表。新增渠道在此加一行即可。
PROFILES: dict[str, PlatformProfile] = {
    # ---- 跨境（佣金已核实；物流/代发为估算）----
    "tiktok_us": PlatformProfile(
        key="tiktok_us", name="TikTok Shop 美国", cross_border=True, currency="US$",
        fx_to_rmb=FX_USD, commission_rate=0.06, fulfillment_rmb=25.0, dropship_fee_rmb=3.0,
        return_rate=0.05, sell_multiple=3.5,
        note="佣金6%官方核实(2024-04起,全类目含服装鞋帽);物流25/代发3为估算待校准;另有退款行政费未计",
    ),
    "tiktok_uk": PlatformProfile(
        key="tiktok_uk", name="TikTok Shop 英国", cross_border=True, currency="£",
        fx_to_rmb=FX_GBP, commission_rate=0.09, fulfillment_rmb=22.0, dropship_fee_rmb=3.0,
        return_rate=0.05, sell_multiple=3.5,
        note="佣金9%标准类目核实;GBP汇率9.2为估算;物流/代发估算待校准",
    ),
    "aliexpress": PlatformProfile(
        key="aliexpress", name="速卖通 AliExpress", cross_border=True, currency="US$",
        fx_to_rmb=FX_USD, commission_rate=0.135, fulfillment_rmb=20.0, dropship_fee_rmb=3.0,
        return_rate=0.04, sell_multiple=3.0,
        note="佣金8%(服装鞋)+交易服务费2.5%核实+支付费~3%估,合计13.5%;物流/代发估算待校准",
    ),
    # ---- 国内（佣金多数核实；物流/代发/退货为估算；拼多多闲鱼扣点未充分验证）----
    "tmall": PlatformProfile(
        key="tmall", name="天猫", cross_border=False, currency="¥",
        fx_to_rmb=1.0, commission_rate=0.056, fulfillment_rmb=6.0, dropship_fee_rmb=2.0,
        return_rate=0.10, sell_multiple=1.6,
        note="技术服务费5%(服装)+基础软件费0.6%核实;物流/代发/退货估算",
    ),
    "taobao": PlatformProfile(
        key="taobao", name="淘宝", cross_border=False, currency="¥",
        fx_to_rmb=1.0, commission_rate=0.006, fulfillment_rmb=6.0, dropship_fee_rmb=2.0,
        return_rate=0.10, sell_multiple=1.6,
        note="基础软件费0.6%核实(2024-09起);物流/代发/退货估算",
    ),
    "douyin": PlatformProfile(
        key="douyin", name="抖音小店", cross_border=False, currency="¥",
        fx_to_rmb=1.0, commission_rate=0.05, fulfillment_rmb=6.0, dropship_fee_rmb=2.0,
        return_rate=0.12, sell_multiple=1.6,
        note="服装技术服务费5%(中等置信);物流/代发/退货估算;退货率偏高(直播冲动消费)",
    ),
    "pdd": PlatformProfile(
        key="pdd", name="拼多多", cross_border=False, currency="¥",
        fx_to_rmb=1.0, commission_rate=0.006, fulfillment_rmb=6.0, dropship_fee_rmb=2.0,
        return_rate=0.12, sell_multiple=1.4,
        note="技术服务费~0.6%(未充分验证);加价空间低(走量);物流/代发/退货估算",
    ),
    "xianyu": PlatformProfile(
        key="xianyu", name="闲鱼", cross_border=False, currency="¥",
        fx_to_rmb=1.0, commission_rate=0.0, fulfillment_rmb=6.0, dropship_fee_rmb=2.0,
        return_rate=0.05, sell_multiple=1.6,
        note="C2C个人闲置基本免佣(未充分验证);物流/代发/退货估算",
    ),
}

# 可被外部 JSON 覆盖的参数（用户用真实数据校准时改这些，不必改源码）
_OVERRIDABLE = {
    "commission_rate", "fulfillment_rmb", "dropship_fee_rmb",
    "return_rate", "sell_multiple", "fx_to_rmb", "fixed_fee_rmb",
}


def _apply_overrides(profiles: dict, path: Path | None = None) -> dict:
    """用 data/platform_profiles.json 覆盖默认参数（真实数据校准入口，无文件则原样）。

    JSON 形如 {"tiktok_us": {"commission_rate": 0.06, "fulfillment_rmb": 30}, ...}，
    只接受 _OVERRIDABLE 字段，其余忽略；读不出/格式错则静默跳过。
    """
    path = path or Path(config.PROJECT_ROOT) / "data" / "platform_profiles.json"
    if not path.exists():
        return profiles
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return profiles
    for key, fields in raw.items():
        if key in profiles and isinstance(fields, dict):
            upd = {k: float(v) for k, v in fields.items() if k in _OVERRIDABLE}
            if upd:
                profiles[key] = replace(profiles[key], **upd)
    return profiles


PROFILES = _apply_overrides(PROFILES)

# 默认渠道分组（agent 缺省用）
DEFAULT_OVERSEAS = ["tiktok_us", "aliexpress"]
DEFAULT_DOMESTIC = ["xianyu", "pdd", "douyin"]


@dataclass
class PlatformQuote:
    """某商品在某渠道的测算结果。"""
    platform: str
    currency: str
    cross_border: bool
    resale_local: float     # 目标售价（本币，心理价）
    resale_rmb: float       # 目标售价（RMB 口径）
    profit: float           # 净利润（RMB）
    margin: float           # 净利率（0-1）


@dataclass
class PlatformPick:
    """选品决策：货源商品 + 推荐渠道 + 各渠道利润对比 + 评分。"""
    item: SourcedItem
    best: PlatformQuote                       # 利润最高的渠道
    quotes: list[PlatformQuote] = field(default_factory=list)
    score: float = 0.0
    reason: str = ""


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def psych_local(x: float, cross_border: bool) -> float:
    """心理价：跨境取 .99 结尾（外币），国内取 .9 结尾（人民币）。"""
    if not cross_border:
        return psych_price(x)
    base = math.floor(x) + 0.99
    return round(base if base >= x else base + 1, 2)


def estimate_freight(cost: float, p: PlatformProfile) -> float:
    """物流费按商品大小粗分档（进价作大小的粗代理，无重量数据时的近似）。
    profile.fulfillment_rmb 为小件基准；中件×2.5、大件×5。
    ⚠️ 仍是估算，重货/大件务必按真实重量与物流报价核算。"""
    base = p.fulfillment_rmb
    if cost <= 50:
        return base
    if cost <= 150:
        return base * 2.5
    return base * 5.0


def quote(item: SourcedItem, p: PlatformProfile) -> PlatformQuote:
    """测算一个商品在一个渠道的售价与净利润（无货源口径：进价=代发价）。"""
    resale_local = psych_local(item.cost_price * p.sell_multiple / p.fx_to_rmb, p.cross_border)
    resale_rmb = resale_local * p.fx_to_rmb
    profit = (
        resale_rmb - item.cost_price
        - resale_rmb * p.commission_rate
        - resale_rmb * p.return_rate
        - estimate_freight(item.cost_price, p)
        - p.dropship_fee_rmb
        - p.fixed_fee_rmb
    )
    margin = profit / resale_rmb if resale_rmb > 0 else 0.0
    return PlatformQuote(
        platform=p.name, currency=p.currency, cross_border=p.cross_border,
        resale_local=resale_local, resale_rmb=round(resale_rmb, 2),
        profit=round(profit, 2), margin=round(margin, 3),
    )


def _score(item: SourcedItem, profit: float, margin: float, cross_border: bool) -> float:
    """综合评分 0-100：净利率 + 销量信号 + 单件净利。跨境单件利润目标更高。"""
    margin_score = _clamp(margin / 0.45)
    if margin > 0.7:
        margin_score *= 0.7
    sales_score = _clamp(math.log10(item.sales + 1) / math.log10(2000))
    profit_full = 50.0 if cross_border else 30.0   # 单件净利满分线
    profit_score = _clamp(profit / profit_full)
    return round(100 * (0.40 * margin_score + 0.35 * sales_score + 0.25 * profit_score), 1)


def _reason(item: SourcedItem, best: PlatformQuote, others: list[PlatformQuote]) -> str:
    bits = [f"推荐 {best.platform} 卖：售价≈{best.currency}{best.resale_local} "
            f"单件净利¥{best.profit:.0f}（净利率{best.margin*100:.0f}%）"]
    rest = [q for q in others if q.platform != best.platform]
    if rest:
        cmp = "，".join(f"{q.platform}净利¥{q.profit:.0f}" for q in rest)
        bits.append(f"对比：{cmp}")
    if item.sales >= 2000:
        bits.append("销量爆款需求稳")
    elif item.sales >= 500:
        bits.append("销量可观")
    return "；".join(bits)


def resolve_profiles(markets: list[str] | None) -> list[PlatformProfile]:
    """按 key 列表取渠道档；None/空/全未知 时回退跨境默认。未知 key 跳过。"""
    if not markets:
        return [PROFILES[k] for k in DEFAULT_OVERSEAS]
    out = [PROFILES[k] for k in markets if k in PROFILES]
    return out or [PROFILES[k] for k in DEFAULT_OVERSEAS]


def select_platforms(
    items: list[SourcedItem],
    markets: list[str] | None = None,
    query: SourcingQuery | None = None,
    min_score: float = 0.0,
    top_k: int = 0,
) -> list[PlatformPick]:
    """对候选货源在指定渠道测算利润，取最优渠道，打分排序。亏本（最优净利≤0）剔除。"""
    profiles = resolve_profiles(markets)
    picks: list[PlatformPick] = []
    for it in items:
        if it.cost_price <= 0:
            continue
        quotes = [quote(it, p) for p in profiles]
        best = max(quotes, key=lambda q: q.profit)
        if best.profit <= 0:
            continue
        score = _score(it, best.profit, best.margin, best.cross_border)
        if score < min_score:
            continue
        picks.append(PlatformPick(
            item=it, best=best, quotes=quotes, score=score,
            reason=_reason(it, best, quotes),
        ))
    picks.sort(key=lambda p: p.score, reverse=True)
    return picks[:top_k] if top_k > 0 else picks
