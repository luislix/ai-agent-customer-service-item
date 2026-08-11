"""选品打分与定价：把货源商品转成选品决策（建议转售价 / 毛利 / 综合评分）。

纯规则、确定性逻辑（算钱的事不交给 LLM，更可靠可复现）：
  - 定价：进货价加成 + 保底毛利，向上取到心理价（.9 结尾）。
  - 评分：毛利率 + 销量（需求信号）+ 单件毛利，加权到 0-100，便于排序选爆款。
"""
from __future__ import annotations

import math

from .types import SourcedItem, SourcedPick, SourcingQuery


def psych_price(x: float) -> float:
    """向上取到「心理价」：个位为 9（<10 取 9.9 档）。如 35.1->39, 128->129, 6.2->9.9。"""
    if x <= 9.9:
        return 9.9
    n = math.ceil(x)
    # 个位补到 9
    if n % 10 == 0:
        return float(n - 1)
    return float(n + (9 - n % 10)) if n % 10 < 9 else float(n)


def suggest_resale(cost: float, markup: float = 0.6, min_profit: float = 10.0) -> float:
    """建议转售价：max(进货价×(1+加成), 进货价+保底毛利)，再取心理价。"""
    base = max(cost * (1 + markup), cost + min_profit)
    return psych_price(base)


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def score_item(item: SourcedItem, resale: float) -> tuple[float, float, float]:
    """返回 (综合评分 0-100, 单件毛利, 毛利率)。"""
    profit = resale - item.cost_price
    margin = profit / resale if resale > 0 else 0.0

    # 毛利率：40% 为佳，<15% 几乎不赚，>70% 多半定价虚高/不好卖
    margin_score = _clamp(margin / 0.45)
    if margin > 0.7:
        margin_score *= 0.7
    # 销量：需求信号，log 压缩（2000 单≈满分）
    sales_score = _clamp(math.log10(item.sales + 1) / math.log10(2000))
    # 单件毛利：绝对赚头，30 元≈满分（无货源低客单，毛利别太薄）
    profit_score = _clamp(profit / 30.0)

    score = 100 * (0.40 * margin_score + 0.35 * sales_score + 0.25 * profit_score)
    return round(score, 1), round(profit, 2), round(margin, 3)


def _reason(item: SourcedItem, profit: float, margin: float) -> str:
    bits = []
    if item.sales >= 2000:
        bits.append("销量爆款需求稳")
    elif item.sales >= 500:
        bits.append("销量可观")
    if margin >= 0.5:
        bits.append(f"毛利率{margin*100:.0f}%空间大")
    elif margin >= 0.3:
        bits.append(f"毛利率{margin*100:.0f}%健康")
    bits.append(f"单件赚约¥{profit:.0f}")
    return "；".join(bits)


def select(
    items: list[SourcedItem],
    query: SourcingQuery | None = None,
    markup: float = 0.6,
    min_profit: float = 10.0,
    min_score: float = 0.0,
    top_k: int = 0,
) -> list[SourcedPick]:
    """对候选货源定价+打分，过滤后按评分降序返回选品决策。

    query.min_sales 已在搜索层过滤，这里只做定价/评分/排序与可选 min_score/top_k 截断。
    """
    picks: list[SourcedPick] = []
    for it in items:
        if it.cost_price <= 0:
            continue
        resale = suggest_resale(it.cost_price, markup, min_profit)
        score, profit, margin = score_item(it, resale)
        if score < min_score:
            continue
        picks.append(SourcedPick(
            item=it, resale_price=resale, profit=profit, margin=margin,
            score=score, reason=_reason(it, profit, margin),
        ))
    picks.sort(key=lambda p: p.score, reverse=True)
    return picks[:top_k] if top_k > 0 else picks
