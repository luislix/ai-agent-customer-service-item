from __future__ import annotations

import time
from collections.abc import Iterable
from typing import Callable

from .models import CrawlConfig, CrawlFailure, ItemDetail, SearchItem
from .normalize import normalize_detail
from .providers.base import DetailProvider, ProviderError, SearchProvider


def collect(
    keywords: Iterable[str],
    search_provider: SearchProvider,
    detail_provider: DetailProvider,
    config: CrawlConfig,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[list[dict], list[CrawlFailure], list[ItemDetail]]:
    records, failures, raw_details = [], [], []
    seen: set[str] = set()
    normalized_keywords = _keywords(keywords)
    for keyword in normalized_keywords:
        keyword_count = 0
        cursor = None
        while keyword_count < config.per_keyword_limit:
            try:
                page = _retry(lambda: search_provider.search(keyword, cursor, config.page_size), config, sleep)
            except Exception as exc:  # one keyword should not hide other test data
                _raise_auth_error(exc)
                failures.append(CrawlFailure(keyword, None, "search", str(exc)))
                break
            if not page.items:
                break
            for candidate in page.items:
                if keyword_count >= config.per_keyword_limit:
                    break
                if config.total_limit is not None and len(records) >= config.total_limit:
                    return records, failures, raw_details
                if candidate.item_id in seen:
                    continue
                seen.add(candidate.item_id)
                keyword_count += 1
                try:
                    detail = _retry(lambda candidate=candidate: detail_provider.get_detail(candidate.item_id), config, sleep)
                    record = normalize_detail(detail)
                    records.append(record)
                    raw_details.append(detail)
                except Exception as exc:  # one bad product must not stop the batch
                    _raise_auth_error(exc)
                    failures.append(CrawlFailure(keyword, candidate.item_id, "detail", str(exc)))
                if config.delay_seconds:
                    sleep(config.delay_seconds)
            if not page.next_cursor or page.next_cursor == cursor:
                break
            cursor = page.next_cursor
    return records, failures, raw_details


def _retry(call, config: CrawlConfig, sleep):
    for attempt in range(config.max_retries + 1):
        try:
            return call()
        except ProviderError as exc:
            _raise_auth_error(exc)
            if attempt >= config.max_retries:
                raise
            if config.retry_backoff_seconds:
                sleep(config.retry_backoff_seconds * (2**attempt))


def _raise_auth_error(exc: Exception) -> None:
    message = str(exc).lower()
    if "http 401" in message or "http 403" in message or "authentication" in message or "unauthorized" in message:
        raise RuntimeError(f"授权数据源认证失败，已停止：{exc}") from exc


def _keywords(values: Iterable[str]) -> list[str]:
    result, seen = [], set()
    for value in values:
        keyword = str(value).strip()
        if keyword and keyword not in seen:
            result.append(keyword)
            seen.add(keyword)
    return result
