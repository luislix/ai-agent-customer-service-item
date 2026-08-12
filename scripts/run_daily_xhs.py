"""只生成小红书每日人工发布包，不调用微信接口。

    python -m scripts.run_daily_xhs
    python -m scripts.run_daily_xhs --source-date 2026-08-10
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import config  # noqa: E402
from src.modules.promotion.store import PromotionStore  # noqa: E402
from src.modules.promotion.xhs_job import run_daily_xhs  # noqa: E402
from src.modules.sourcing.store import SourcingPickStore  # noqa: E402
from src.llm.factory import build_llm  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-date", default=None, help="选品日期 YYYY-MM-DD，默认昨天")
    parser.add_argument("--output-root", default=None, help="发布包输出根目录，默认 data/promotion")
    args = parser.parse_args()
    result = run_daily_xhs(
        SourcingPickStore(config.DB_PATH), PromotionStore(config.DB_PATH),
        llm=build_llm(), source_date=args.source_date, output_root=args.output_root,
    )
    print(result)
    return 0 if result.get("saved", 0) or result.get("reason") in {"no_approved_pick", "duplicate"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
