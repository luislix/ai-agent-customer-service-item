from __future__ import annotations

from typing import Protocol

from ..models import ItemDetail, SearchPage


class ProviderError(RuntimeError):
    """数据源不可用或返回不符合授权适配器契约。"""


class SearchProvider(Protocol):
    def search(self, keyword: str, cursor: str | None, page_size: int) -> SearchPage:
        ...


class DetailProvider(Protocol):
    def get_detail(self, item_id: str) -> ItemDetail:
        ...
