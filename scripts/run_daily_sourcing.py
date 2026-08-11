"""每日定时选品（cron/守护进程调用）：跑选品落库，打印当日待勾选清单。

    python -m scripts.run_daily_sourcing                 # 用 config.SOURCING_KEYWORDS
    python -m scripts.run_daily_sourcing 手机支架 宠物玩具  # 指定关键词

cron 示例（每天 9:00）：
    0 9 * * * cd /path/to/project && python -m scripts.run_daily_sourcing >> logs/sourcing.log 2>&1

走 Orchestrator.run_sourcing_job：选品模块 MANUAL（数据源降级/养号暂停）时自动跳过。
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:  # noqa: BLE001
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import config  # noqa: E402
from src.modules.sourcing.store import SourcingPickStore  # noqa: E402
from src.orchestrator import Orchestrator  # noqa: E402


def main(argv: list[str]) -> int:
    keywords = [a for a in argv if not a.startswith("--")] or \
        [x.strip() for x in (config.SOURCING_KEYWORDS or "").split(",") if x.strip()]
    if not keywords:
        print("没有关键词（设 SOURCING_KEYWORDS 或命令行传入）")
        return 1

    orch = Orchestrator()
    summary = orch.run_sourcing_job(keywords)
    if summary is None:
        print("选品模块处于 MANUAL，已跳过本次选品。")
        return 0

    print(f"选品完成 {summary['run_date']}，新落库 {summary['saved']} 条")
    for kw, r in summary["keywords"].items():
        print(f"  {kw}: 跨境 {r.get('overseas', 0)} / 国内 {r.get('domestic', 0)}")

    store = SourcingPickStore(config.DB_PATH)
    pend = store.list_pending(run_date=summary["run_date"])
    print(f"\n待人工勾选 {len(pend)} 条（按评分 Top15）：")
    for p in pend[:15]:
        print(f"  #{p.id} [{p.group}] 分{p.score:<5} {p.title[:24]} "
              f"进价¥{p.cost_price:g} ★{p.platform} {p.currency}{p.resale_local:g} 净利¥{p.profit:g}")
    print("\n人工勾选：SourcingPickStore(db).approve(id) / .reject(id)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
