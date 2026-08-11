from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

from ..models import ItemDetail, SearchItem, SearchPage
from .base import ProviderError


class HttpJsonProvider:
    """参考授权 API 适配器。

    API 契约：GET /search?keyword=...&cursor=...&page_size=... 返回
    {"items":[{"item_id":"...","source_url":"..."}],"next_cursor":"..."}；
    GET /items/{item_id} 返回 {"item_id":"...","source_url":"...","payload":{...}}。
    真实授权 API 若字段不同，应新增适配器，不要在此处猜测平台私有协议。
    """

    def __init__(self, base_url: str, token: str | None = None, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/") + "/"
        self.token = token
        self.timeout = timeout

    def search(self, keyword: str, cursor: str | None, page_size: int) -> SearchPage:
        query = {"keyword": keyword, "page_size": str(page_size)}
        if cursor is not None:
            query["cursor"] = cursor
        payload = self._get("search?" + urlencode(query))
        rows = payload.get("items")
        if not isinstance(rows, list):
            raise ProviderError("授权搜索响应缺少 items 数组")
        items = []
        for row in rows:
            if not isinstance(row, dict) or not str(row.get("item_id", "")).strip():
                raise ProviderError("授权搜索项缺少 item_id")
            item_id = str(row["item_id"])
            items.append(SearchItem(item_id, str(row.get("source_url") or f"https://www.goofish.com/item?id={item_id}"), row))
        next_cursor = payload.get("next_cursor")
        return SearchPage(items, str(next_cursor) if next_cursor not in (None, "") else None)

    def get_detail(self, item_id: str) -> ItemDetail:
        payload = self._get("items/" + item_id)
        detail_id = str(payload.get("item_id") or item_id)
        body = payload.get("payload", payload)
        if not isinstance(body, dict):
            raise ProviderError("授权详情响应的 payload 必须是 object")
        return ItemDetail(detail_id, str(payload.get("source_url") or f"https://www.goofish.com/item?id={detail_id}"), body)

    def _get(self, path: str) -> dict:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = Request(urljoin(self.base_url, path), headers=headers, method="GET")
        try:
            with urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise ProviderError(f"授权 API HTTP {exc.code}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ProviderError(f"授权 API 请求失败：{exc}") from exc
        if not isinstance(result, dict):
            raise ProviderError("授权 API 响应必须是 object")
        return result
