"""justoneapi 货源搜索客户端：按次计费的多平台聚合 API（覆盖 1688/拼多多/淘宝）。

端点形如：
    https://api.justoneapi.com/api/1688/search-item-list/v1?token=TOKEN&keyword=关键词
大陆专用接入：http://47.117.133.51:30015（域名国内可能不稳，BASE 默认走此 IP）。
认证只需 token 走 query，和万邦风格一致。返回顶层 code="0" 为成功。

注意：搜索接口只有 token+keyword 两个参数，**不支持分页与价格筛选**，
价格/销量过滤在本地做（行为对齐 onebound 离线样例）。

返回是 1688 原始卡片结构，商品在 data.data.OFFER.items[i].data；字段映射见 _parse_items。
无 token 时退化为离线样例，保证链路可离线跑通。
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request

from ...config import config
from .onebound_client import _decode, _offline_samples, _to_float, _to_int
from .types import SourcedItem, SourcingQuery

_PLATFORM_PATH = {"1688": "1688", "阿里": "1688", "pdd": "pdd", "拼多多": "pdd", "taobao": "taobao", "淘宝": "taobao"}

# code -> 人话，方便打印
_CODE_MSG = {
    "0": "成功", "100": "Token 无效", "301": "采集失败",
    "302": "超出速率限制", "303": "超出每日配额", "400": "参数错误",
}

_TAG_RE = re.compile(r"<[^>]+>")
_MAX_RETRY = 2   # 301 采集失败时的最大重试次数


class JustOneApiClient:
    """货源搜索客户端。available=False（未配 token）时 search() 返回离线样例。"""

    name = "justoneapi"

    def __init__(self, token: str | None = None, base: str | None = None):
        self.token = token if token is not None else config.JUSTONEAPI_TOKEN
        self.base = (base or config.JUSTONEAPI_BASE).rstrip("/")
        # 该接口不返回配额字段，保留属性与 OneboundClient 接口一致
        self.last_quota: dict | None = None

    @property
    def available(self) -> bool:
        return bool(self.token)

    def search(self, query: SourcingQuery) -> list[SourcedItem]:
        if not self.available:
            return _offline_samples(query)
        platform = _PLATFORM_PATH.get(query.platform, "1688")
        params = {"token": self.token, "keyword": query.keyword}
        url = f"{self.base}/api/{platform}/search-item-list/v1?" + urllib.parse.urlencode(params)
        data: dict = {}
        for attempt in range(_MAX_RETRY + 1):
            req = urllib.request.Request(url, headers={"User-Agent": "sourcing/1.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(_decode(resp.read()))
            # 301=采集失败(源站抓取失败)，官方提示重试；其余 code 直接走后续处理
            if str(data.get("code", "")) != "301" or attempt >= _MAX_RETRY:
                break
            print(f"[JUSTONEAPI] code=301 采集失败，重试 {attempt + 1}/{_MAX_RETRY}…")
        code = str(data.get("code", ""))
        if code not in ("", "0"):
            print(f"[JUSTONEAPI] 接口异常 code={code}（{_CODE_MSG.get(code, '未知')}）"
                  f" message={data.get('message', '')}")
            return []
        items = _parse_items(data, platform)
        return _apply_filter(items, query)


def _clean_title(t: str) -> str:
    """1688 标题里带 <font color=red> 高亮标签，去掉。"""
    return _TAG_RE.sub("", t or "").strip()


def _locate_rows(data: dict) -> list:
    """商品在 data.data.OFFER.items；带兜底以防结构微调。data 为顶层返回。"""
    node = data.get("data")
    if isinstance(node, dict):
        inner = node.get("data")
        if isinstance(inner, dict):
            offer = inner.get("OFFER")
            if isinstance(offer, dict) and isinstance(offer.get("items"), list):
                return offer["items"]
    return _deep_find_rows(data)


def _deep_find_rows(o, depth: int = 0) -> list:
    """兜底：递归找含 'items' 列表的节点，或第一个元素为 dict 的非空列表。"""
    if depth > 5 or not isinstance(o, (dict, list)):
        return []
    if isinstance(o, dict):
        v = o.get("items")
        if isinstance(v, list) and v and isinstance(v[0], dict):
            return v
        for val in o.values():
            found = _deep_find_rows(val, depth + 1)
            if found:
                return found
    return []


def _parse_items(data: dict, platform: str) -> list[SourcedItem]:
    """把 justoneapi 1688 搜索返回解析成 SourcedItem 列表。每行真实字段在 row['data']。"""
    out: list[SourcedItem] = []
    for row in _locate_rows(data):
        it = row.get("data") if isinstance(row, dict) else None
        if not isinstance(it, dict):
            continue
        price_info = it.get("priceInfo") if isinstance(it.get("priceInfo"), dict) else {}
        after = it.get("afterPrice") if isinstance(it.get("afterPrice"), dict) else {}
        # 销量优先用「已售X」文本（成交量），缺失回退 bookedCount
        sales = _to_int(after.get("text")) or _to_int(it.get("bookedCount"))
        out.append(SourcedItem(
            item_id=str(it.get("offerId") or ""),
            title=_clean_title(it.get("title", "")),
            cost_price=_to_float(price_info.get("price")),
            platform=platform,
            sales=sales,
            pic_url=str(it.get("offerPicUrl") or "").split(",")[0].strip(),
            detail_url=str(it.get("linkUrl") or ""),
            seller=str(it.get("loginId") or ""),
        ))
    return out


def _apply_filter(items: list[SourcedItem], query: SourcingQuery) -> list[SourcedItem]:
    """接口不支持筛选，价格/销量过滤在本地做（对齐 onebound 行为）。"""
    lo, hi = query.min_price, query.max_price
    return [
        it for it in items
        if it.sales >= query.min_sales
        and it.cost_price >= lo
        and (hi == 0 or it.cost_price <= hi)
    ]
