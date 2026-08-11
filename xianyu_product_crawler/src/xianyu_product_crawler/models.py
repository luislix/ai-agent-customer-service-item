from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SearchItem:
    item_id: str
    source_url: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SearchPage:
    items: list[SearchItem]
    next_cursor: str | None = None


@dataclass(frozen=True)
class ItemDetail:
    item_id: str
    source_url: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class CrawlFailure:
    keyword: str
    item_id: str | None
    stage: str
    error: str


@dataclass(frozen=True)
class CrawlConfig:
    per_keyword_limit: int = 20
    total_limit: int | None = 50
    page_size: int = 10
    delay_seconds: float = 2.0
    max_retries: int = 2
    retry_backoff_seconds: float = 1.0
    keep_raw: bool = True

    def __post_init__(self) -> None:
        if self.per_keyword_limit < 1 or self.page_size < 1:
            raise ValueError("per_keyword_limit 和 page_size 必须大于 0")
        if self.total_limit is not None and self.total_limit < 1:
            raise ValueError("total_limit 必须大于 0")
        if self.delay_seconds < 0 or self.retry_backoff_seconds < 0:
            raise ValueError("延迟参数不能小于 0")
        if self.max_retries < 0:
            raise ValueError("max_retries 不能小于 0")
