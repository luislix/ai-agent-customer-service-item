"""极简调度判断（纯函数，零依赖，便于测试）。

守护进程每分钟问一次 should_run：到达运行时点、且今天还没跑过 -> True。
用"上次运行日期"去重，保证一天只触发一次，进程重启也不会漏跑/重跑。
"""
from __future__ import annotations

import datetime


def should_run(now: datetime.datetime, run_hour: int, last_run_date: str | None) -> bool:
    """now 已过当日 run_hour 点，且今天（YYYY-MM-DD）还没跑过则 True。"""
    today = now.date().isoformat()
    return now.hour >= run_hour and last_run_date != today
