from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..models import ItemDetail, SearchItem, SearchPage
from .base import ProviderError


class FixtureProvider:
    """离线回归数据源，格式见 fixtures/provider.json。"""

    def __init__(self, path: str | Path):
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ProviderError("fixture 根节点必须是 object")
        self._search = payload.get("search", {})
        self._details = payload.get("details", {})
        if not isinstance(self._search, dict) or not isinstance(self._details, dict):
            raise ProviderError("fixture 的 search/details 必须是 object")

    def search(self, keyword: str, cursor: str | None, page_size: int) -> SearchPage:
        rows = self._search.get(keyword, [])
        if not isinstance(rows, list):
            raise ProviderError(f"fixture 搜索结果非法：{keyword}")
        offset = int(cursor or 0)
        page = rows[offset : offset + page_size]
        items = [self._search_item(row) for row in page]
        next_cursor = str(offset + page_size) if offset + page_size < len(rows) else None
        return SearchPage(items, next_cursor)

    def get_detail(self, item_id: str) -> ItemDetail:
        row = self._details.get(item_id)
        if not isinstance(row, dict):
            raise ProviderError(f"fixture 缺少详情：{item_id}")
        source_url = str(row.get("source_url") or f"https://www.goofish.com/item?id={item_id}")
        payload = row.get("payload", row)
        if not isinstance(payload, dict):
            raise ProviderError(f"fixture 详情非法：{item_id}")
        return ItemDetail(item_id, source_url, payload)

    @staticmethod
    def _search_item(row: Any) -> SearchItem:
        if not isinstance(row, dict) or not str(row.get("item_id", "")).strip():
            raise ProviderError("fixture 搜索项必须含 item_id")
        item_id = str(row["item_id"])
        return SearchItem(item_id, str(row.get("source_url") or f"https://www.goofish.com/item?id={item_id}"), row)
