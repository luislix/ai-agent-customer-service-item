"""Onebound（万邦）货源搜索客户端：付费聚合 API，覆盖 1688 / 拼多多。

端点形如：
    https://api-gw.onebound.cn/1688/item_search/?key=KEY&secret=SECRET&q=关键词&page=1
基础版直接用 key+secret 走 query，无复杂签名；返回 JSON，error_code="0000" 为成功，
商品在 items.item[]。零 Python 第三方依赖（urllib），和项目其它接入风格一致。

无 ONEBOUND_API_KEY 时退化为离线样例数据，保证整条选品->推广链路可离线跑通。
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

from ...config import config
from .types import SourcedItem, SourcingQuery

_BASE = "https://api-gw.onebound.cn"
_PLATFORM_ALIAS = {"1688": "1688", "pdd": "pdd", "拼多多": "pdd", "阿里": "1688"}


def _to_float(v, default: float = 0.0) -> float:
    try:
        return float(str(v).replace("¥", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def _to_int(v, default: int = 0) -> int:
    """销量可能是 '已售300+' / '1.2万' / 300 等脏格式，尽量抠出数字。"""
    s = str(v).strip()
    if not s:
        return default
    mult = 1.0
    if "万" in s:
        mult = 10000.0
    digits = "".join(c for c in s if c.isdigit() or c == ".")
    if not digits:
        return default
    try:
        return int(float(digits) * mult)
    except ValueError:
        return default


class OneboundClient:
    """货源搜索客户端。available=False（未配 key）时 search() 返回离线样例。"""

    name = "onebound"

    def __init__(self, api_key: str | None = None, secret: str | None = None):
        self.api_key = api_key if api_key is not None else config.ONEBOUND_API_KEY
        self.secret = secret if secret is not None else config.ONEBOUND_API_SECRET
        # 最近一次真实调用的配额（today/max/expires），离线/未调用时为 None
        self.last_quota: dict | None = None

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def search(self, query: SourcingQuery) -> list[SourcedItem]:
        if not self.available:
            return _offline_samples(query)
        platform = _PLATFORM_ALIAS.get(query.platform, "1688")
        params = {
            "key": self.api_key, "secret": self.secret,
            "q": query.keyword, "page": str(query.page),
            "result_type": "json", "lang": "zh-CN", "cache": "yes",
        }
        if query.min_price:
            params["start_price"] = str(query.min_price)
        if query.max_price:
            params["end_price"] = str(query.max_price)
        url = f"{_BASE}/{platform}/item_search/?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": "sourcing/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(_decode(resp.read()))
        self._report_quota(data)
        return _parse_items(data, platform)

    def _report_quota(self, data: dict) -> None:
        """记录并打印本次调用的配额/错误，让"还能调几次、哪天到期"可见。"""
        self.last_quota = parse_quota(data)
        if self.last_quota:
            q = self.last_quota
            print(
                f"[ONEBOUND] 用量 today={q.get('today', '?')} "
                f"max={q.get('max', '?')} expires={q.get('expires', '?')}"
            )
        code = str(data.get("error_code", data.get("ret", "")))
        if code not in ("", "0000"):
            print(f"[ONEBOUND] 接口异常 error_code={code} reason={data.get('reason', '')}")


def _decode(raw: bytes) -> str:
    """Onebound 有时 Content-Type 谎称 utf-8 实则 GBK（尤其错误响应），
    先按 utf-8 解，失败回退 GBK，避免真实中文数据/报错信息乱码。"""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("gbk", errors="replace")


def parse_quota(data: dict) -> dict | None:
    """从返回的 api_info 抠出配额信息。
    形如 'today:0 max:10 all[2=0+0+2];expires:2026-06-27'
    -> {'today': '0', 'max': '10', 'expires': '2026-06-27', 'raw': '...'}
    无 api_info 时返回 None。"""
    info = str(data.get("api_info") or "").strip()
    if not info:
        return None
    out: dict = {"raw": info}
    for token in info.replace(";", " ").split():
        key, sep, val = token.partition(":")
        if sep and key.lower() in ("today", "max", "expires"):
            out[key.lower()] = val.strip()
    return out


def _parse_items(data: dict, platform: str) -> list[SourcedItem]:
    """把 Onebound item_search 返回解析成 SourcedItem 列表。容忍字段缺失。"""
    code = str(data.get("error_code", data.get("ret", "")))
    if code not in ("", "0000"):  # 0000=成功；其它（如 2000 无结果 / 配额）原样返回空
        return []
    raw = data.get("items", {})
    items = raw.get("item", raw) if isinstance(raw, dict) else raw
    if isinstance(items, dict):
        items = [items]
    out: list[SourcedItem] = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        out.append(SourcedItem(
            item_id=str(it.get("num_iid") or it.get("item_id") or it.get("id") or ""),
            title=str(it.get("title") or it.get("subject") or "").strip(),
            cost_price=_to_float(it.get("price") or it.get("promotion_price") or it.get("orginal_price")),
            platform=platform,
            sales=_to_int(it.get("sales") or it.get("sold") or it.get("sale_count")),
            pic_url=str(it.get("pic_url") or it.get("pic") or ""),
            detail_url=str(it.get("detail_url") or it.get("item_url") or ""),
            seller=str(it.get("seller_nick") or it.get("shop_title") or it.get("nick") or ""),
        ))
    return out


def _offline_samples(query: SourcingQuery) -> list[SourcedItem]:
    """无 key 时的离线样例：围绕关键词造几条不同价位/销量的货源，供链路演示与测试。"""
    kw = query.keyword or "好物"
    seeds = [
        (f"{kw} 厂家直供 现货批发", 18.5, 5200),
        (f"{kw} 升级款 高品质 包邮", 32.0, 1800),
        (f"{kw} 基础款 走量低价", 9.9, 12000),
        (f"{kw} 礼盒装 送礼优选", 56.0, 430),
        (f"{kw} 旗舰版 全配件", 88.0, 260),
    ]
    items = [
        SourcedItem(
            item_id=f"OFFLINE-{i+1}", title=title, cost_price=cost,
            platform=_PLATFORM_ALIAS.get(query.platform, "1688"),
            sales=sales, pic_url="", detail_url="",
            seller="样例供应商",
        )
        for i, (title, cost, sales) in enumerate(seeds)
    ]
    # 应用 query 的价格/销量过滤，行为和真实 search 一致
    lo, hi = query.min_price, query.max_price
    return [
        it for it in items
        if it.sales >= query.min_sales
        and it.cost_price >= lo
        and (hi == 0 or it.cost_price <= hi)
    ]
