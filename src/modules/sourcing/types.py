"""选品模块数据结构。

进货侧（货源平台搜到的商品）-> 选品决策（建议转售价/利润/评分）-> 喂给推广/客服模块。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SourcingQuery:
    """一次选品搜索条件。"""
    keyword: str
    platform: str = "1688"      # 1688 / pdd（拼多多）
    min_price: float = 0.0      # 进货价下限（元）
    max_price: float = 0.0      # 进货价上限（0=不限）
    min_sales: int = 0          # 最低销量门槛（过滤滞销）
    page: int = 1
    page_size: int = 20


@dataclass
class SourcedItem:
    """从货源平台搜到的一个商品（进货侧原始数据）。"""
    item_id: str
    title: str
    cost_price: float           # 进货价（元）
    platform: str = "1688"
    sales: int = 0              # 销量/成交量
    pic_url: str = ""           # 主图
    detail_url: str = ""        # 商品详情页
    seller: str = ""            # 供应商/店铺


@dataclass
class SourcedPick:
    """选品决策结果：货源商品 + 建议转售价 / 单件毛利 / 评分 / 理由。"""
    item: SourcedItem
    resale_price: float         # 建议在闲鱼/小红书卖的价（元）
    profit: float               # 单件毛利（元）
    margin: float               # 毛利率（0-1）
    score: float                # 综合评分（0-100，越高越值得上架）
    reason: str = ""            # 选它的理由（给人看 / 写进种草帖）
