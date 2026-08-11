"""选品定时守护进程（纯标准库，零依赖，跨平台）。

每天到 SOURCING_RUN_HOUR 点自动跑一次每日选品（经 Orchestrator，模块 MANUAL 时跳过）。
进程常驻，每 60 秒检查一次；用"上次运行日期"去重，一天只跑一次、重启不漏不重。

    python -m scripts.run_scheduler

更省资源的替代：用系统计划任务直接调 run_daily_sourcing（见 README / 下方注释），
免常驻进程。Windows 计划任务示例（每天 9:00）：
    schtasks /create /tn "DailySourcing" /tr "python -m scripts.run_daily_sourcing" /sc daily /st 09:00
"""
from __future__ import annotations

import datetime
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:  # noqa: BLE001
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import config  # noqa: E402
from src.core.scheduler import should_run  # noqa: E402
from src.modules.sourcing.store import SourcingPickStore  # noqa: E402
from src.orchestrator import Orchestrator  # noqa: E402

_POLL_SECONDS = 60


def _run_once(orch: Orchestrator, keywords: list[str]) -> None:
    summary = orch.run_sourcing_job(keywords)
    if summary is None:
        print(f"[{_now()}] 选品模块 MANUAL，已跳过")
        return
    pend = SourcingPickStore(config.DB_PATH).count_pending(summary["run_date"])
    print(f"[{_now()}] 选品完成 {summary['run_date']}，新落库 {summary['saved']} 条，"
          f"当日待勾选 {pend} 条")


def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def main() -> int:
    keywords = [x.strip() for x in (config.SOURCING_KEYWORDS or "").split(",") if x.strip()]
    run_hour = config.SOURCING_RUN_HOUR
    if not keywords:
        print("没有关键词（设 SOURCING_KEYWORDS）")
        return 1

    orch = Orchestrator()
    last_run_date: str | None = None
    print(f"[{_now()}] 选品守护进程启动：每天 {run_hour:02d}:00 跑 {keywords}（每 {_POLL_SECONDS}s 检查）")
    while True:
        now = datetime.datetime.now()
        if should_run(now, run_hour, last_run_date):
            try:
                _run_once(orch, keywords)
            except Exception as e:  # noqa: BLE001 守护进程不因单次异常退出
                print(f"[{_now()}] 选品异常（忽略，明天再试）：{e}")
            last_run_date = now.date().isoformat()
        time.sleep(_POLL_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
