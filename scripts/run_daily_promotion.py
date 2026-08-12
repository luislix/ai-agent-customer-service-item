"""手动生成每日推广内容，用前一天已审核的国内选品。

    python -m scripts.run_daily_promotion
    python -m scripts.run_daily_promotion --source-date 2026-08-10
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import config  # noqa: E402
from src.modules.promotion.store import PromotionStore  # noqa: E402
from src.modules.sourcing.store import SourcingPickStore  # noqa: E402
from src.orchestrator import Orchestrator  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-date", default=None, help="选品日期 YYYY-MM-DD，默认昨天")
    args = parser.parse_args()
    result = Orchestrator().run_promotion_job(
        SourcingPickStore(config.DB_PATH), PromotionStore(config.DB_PATH), source_date=args.source_date,
    )
    if result is None:
        print("推广模块处于 MANUAL，已转人工工单")
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
