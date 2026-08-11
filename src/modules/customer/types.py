"""客服模块数据结构。"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Intent(str, Enum):
    GREETING = "greeting"        # 打招呼/在吗
    BARGAIN = "bargain"          # 议价砍价
    PRODUCT_QA = "product_qa"    # 商品咨询（参数/库存/成色）
    LOGISTICS = "logistics"      # 物流/发货/什么时候到
    AFTERSALE = "aftersale"      # 售后/退换/质量问题
    PURCHASE = "purchase"        # 已拍下/已付款
    OTHER = "other"


@dataclass
class BuyerMessage:
    conversation_id: str
    buyer_id: str
    text: str
    item_id: str = ""
    item_title: str = ""
    item_price: float = 0.0      # 标价
    floor_price: float = 0.0     # 可接受最低价（议价下限，0 表示不让价）
    is_virtual: bool = False     # 虚拟商品（可自动发货）
    paid: bool = False           # 是否已付款


@dataclass
class AgentReply:
    text: str
    intent: Intent
    actions: list[str] = field(default_factory=list)  # create_ship_order / escalate_human ...
    confidence: float = 1.0
