"""采集闲鱼浏览历史商品，生成 JSONL 快照和 Markdown 审阅报告。"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from src.config import config
from src.modules.product_rag.xianyu_snapshot_crawler import (
    browser_discover,
    crawl_details,
    load_item_links,
    write_outputs,
)


def _detail_client(cookie: str):
    vendor = Path(__file__).resolve().parents[1] / "vendor" / "XianYuApis"
    sys.path.insert(0, str(vendor))
    original_cwd = Path.cwd()
    try:
        # XianYuApis 在导入时以当前目录加载 static/ 下的签名脚本。
        os.chdir(vendor)
        from goofish_apis import XianyuApis  # type: ignore
        from utils.goofish_utils import generate_device_id, trans_cookies  # type: ignore
    finally:
        os.chdir(original_cwd)

    api = XianyuApis(trans_cookies(cookie), generate_device_id(trans_cookies(cookie).get("unb", "")))
    return api.get_item_info


def main() -> int:
    parser = argparse.ArgumentParser(description="闲鱼浏览历史商品快照采集")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--from-urls", help="每行一个闲鱼商品 URL 或 item_id")
    source.add_argument("--history-url", help="已登录闲鱼浏览历史页面 URL")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--scrolls", type=int, default=3)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", default="data/product_snapshots.jsonl")
    parser.add_argument("--markdown", default="data/product_snapshots.md")
    parser.add_argument("--errors", default="data/product_snapshot_errors.jsonl")
    args = parser.parse_args()
    if args.limit < 1 or args.delay < 0:
        parser.error("--limit 必须大于 0，--delay 不能小于 0")
    cookie = config.XIANYU_COOKIE or ""
    if args.history_url and not cookie:
        parser.error("浏览器模式需要 XIANYU_COOKIE；不会从文件或输出中保存 Cookie")
    try:
        items = (
            load_item_links(args.from_urls, limit=args.limit)
            if args.from_urls
            else browser_discover(args.history_url, cookie, limit=args.limit, scrolls=args.scrolls)
        )
    except Exception as exc:  # noqa: BLE001
        print(f"发现商品失败：{exc}", file=sys.stderr)
        return 2
    if not items:
        print("未发现商品链接；请检查历史页登录状态或使用 --from-urls", file=sys.stderr)
        return 1
    print("发现商品：" + ", ".join(item.item_id for item in items))
    if args.dry_run:
        return 0
    if not cookie:
        parser.error("详情抓取需要 XIANYU_COOKIE")
    try:
        records, failures = crawl_details(items, _detail_client(cookie), delay=args.delay)
        write_outputs(records, failures, output=args.output, markdown=args.markdown, errors=args.errors)
    except Exception as exc:  # noqa: BLE001
        print(f"详情抓取失败：{exc}", file=sys.stderr)
        return 2
    print(f"写入成功：{len(records)} 条，失败：{len(failures)} 条")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
