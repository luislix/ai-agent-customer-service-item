"""每日选品任务：对一组关键词跑选品（跨境+国内），结果落库成当日选品清单待人工勾选。

可由 cron/守护进程定时触发（见 scripts/run_daily_sourcing.py），
也可经 Orchestrator.run_sourcing_job 调用（带模块状态感知：MANUAL 时跳过）。
每个关键词只调一次数据源接口，跨境/国内两组复用同一批货源。
"""
from __future__ import annotations

import datetime

from .agent import SourcingAgent
from .platforms import DEFAULT_DOMESTIC, DEFAULT_OVERSEAS, select_platforms
from .store import SourcingPickStore
from .types import SourcingQuery

DEFAULT_GROUPS = [("overseas", DEFAULT_OVERSEAS), ("domestic", DEFAULT_DOMESTIC)]


def run_daily_sourcing(
    keywords: list[str],
    store: SourcingPickStore,
    agent: SourcingAgent | None = None,
    groups: list[tuple[str, list[str]]] | None = None,
    top_k: int = 3,
    min_sales: int = 500,
    run_date: str | None = None,
) -> dict:
    """跑一轮每日选品，落库并返回统计 {run_date, saved, keywords:{kw:{group:n}}}。"""
    agent = agent or SourcingAgent()
    groups = groups or DEFAULT_GROUPS
    run_date = run_date or datetime.date.today().isoformat()
    summary: dict = {"run_date": run_date, "saved": 0, "keywords": {}}
    for kw in keywords:
        items = agent.client.search(SourcingQuery(keyword=kw, min_sales=min_sales))
        kw_res: dict = {}
        for gname, markets in groups:
            picks = select_platforms(items, markets=markets, top_k=top_k)
            n = sum(1 for pk in picks if store.save(run_date, kw, gname, pk))
            kw_res[gname] = n
            summary["saved"] += n
        summary["keywords"][kw] = kw_res
    return summary
