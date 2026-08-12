"""打开小红书创作后台，填充一条已审核内容并等待人工发布。

用法：
    python -m scripts.prepare_xhs_browser --content-id 5
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import config  # noqa: E402
from src.modules.promotion.publishing import prepare_xhs_browser  # noqa: E402
from src.modules.promotion.store import PromotionStore  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--content-id", type=int, required=True)
    args = parser.parse_args()
    try:
        output = prepare_xhs_browser(PromotionStore(config.DB_PATH), args.content_id)
    except (RuntimeError, ValueError) as exc:
        print(f"[小红书自动填充失败] {exc}", file=sys.stderr)
        return 1
    print(output)
    print("小红书内容已填入浏览器，请人工检查后点击发布。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
