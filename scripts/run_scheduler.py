"""选品 + 推广定时守护进程（纯标准库，零依赖，跨平台）。

每天到 SOURCING_RUN_HOUR 跑选品，到 PROMOTION_RUN_HOUR 用前一天已审核选品生成推广内容。
SQLite 持久化调度锁保证进程重启后不会重复执行当天任务。

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
from src.core.schedule_store import ScheduleRunStore  # noqa: E402
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


def _run_promotion_once(orch: Orchestrator) -> None:
    summary = orch.run_promotion_job()
    if summary is None:
        print(f"[{_now()}] 推广模块 MANUAL，已转人工工单")
        return
    if summary["saved"]:
        print(f"[{_now()}] 推广内容已生成 #{summary['content_id']}，等待人工审核")
    else:
        print(f"[{_now()}] 推广未生成：{summary['reason']}")


def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def main() -> int:
    keywords = [x.strip() for x in (config.SOURCING_KEYWORDS or "").split(",") if x.strip()]
    if not keywords:
        print("没有关键词（设 SOURCING_KEYWORDS）")
        return 1

    orch = Orchestrator()
    run_store = ScheduleRunStore(config.DB_PATH)
    print(
        f"[{_now()}] 守护进程启动：{config.SOURCING_RUN_HOUR:02d}:00 选品 {keywords}；"
        f"{config.PROMOTION_RUN_HOUR:02d}:00 生成前日已审核推广内容（每 {_POLL_SECONDS}s 检查）"
    )
    while True:
        now = datetime.datetime.now()
        today = now.date().isoformat()
        if now.hour >= config.SOURCING_RUN_HOUR and run_store.start("sourcing", today):
            try:
                _run_once(orch, keywords)
            except Exception as e:  # noqa: BLE001 守护进程不因单次异常退出
                run_store.fail("sourcing", today)
                print(f"[{_now()}] 选品异常，已记录失败：{e}")
            else:
                run_store.complete("sourcing", today)
        if now.hour >= config.PROMOTION_RUN_HOUR and run_store.start("promotion", today):
            try:
                _run_promotion_once(orch)
            except Exception as e:  # noqa: BLE001
                run_store.fail("promotion", today)
                print(f"[{_now()}] 推广异常，已记录失败：{e}")
            else:
                run_store.complete("promotion", today)
        time.sleep(_POLL_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
