from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote_plus

from .automation import AutomationTaskStore
from .build_dataset import build_captures
from .crawl import collect
from .models import CrawlConfig
from .outputs import write_outputs
from .providers import FixtureProvider, HttpJsonProvider
from .receiver import CaptureStore, load_or_create_token, make_handler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="授权数据源商品快照采集器")
    parser.add_argument("--keyword-file", required=True, help="每行一个关键词")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--fixture", help="离线 fixture JSON")
    source.add_argument("--api-base-url", help="授权 API 根地址")
    parser.add_argument("--api-token-env", default="XIANYU_AUTH_API_TOKEN", help="读取 Bearer Token 的环境变量名")
    parser.add_argument("--per-keyword-limit", type=int, default=20)
    parser.add_argument("--total-limit", type=int, default=50)
    parser.add_argument("--page-size", type=int, default=10)
    parser.add_argument("--delay", type=float, default=2.0)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--output", default="out/product_snapshots.jsonl")
    parser.add_argument("--markdown", default="out/review.md")
    parser.add_argument("--errors", default="out/errors.jsonl")
    parser.add_argument("--raw-dir", default="out/raw")
    parser.add_argument("--no-raw", action="store_true")
    return parser


def build_browser_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="使用已登录 Chrome 扩展按关键词自动采集商品")
    parser.add_argument("keyword", nargs="?", help="单个关键词；不传则在终端交互输入")
    parser.add_argument("--capture-root", default="out/captures", help="扩展采集服务根目录")
    parser.add_argument("--output-root", default="out/keyword-runs", help="每次任务的输出根目录")
    parser.add_argument("--port", type=int, default=8765, help="本机控制服务端口")
    parser.add_argument("--token", help="可选固定采集令牌")
    parser.add_argument("--max-items", type=int, default=20)
    parser.add_argument("--delay", type=float, default=2.0)
    parser.add_argument(
        "--search-url-template",
        default="https://www.goofish.com/search?q={keyword}",
        help="闲鱼搜索地址模板，必须包含 {keyword}",
    )
    parser.add_argument("--timeout", type=float, default=900.0, help="任务最长等待秒数")
    return parser


def browser_main(argv: list[str]) -> int:
    args = build_browser_parser().parse_args(argv)
    keyword = (args.keyword or input("请输入关键词：")).strip()
    if not keyword:
        print("采集失败：关键词不能为空", file=sys.stderr)
        return 2
    if "{keyword}" not in args.search_url_template:
        print("采集失败：--search-url-template 必须包含 {keyword}", file=sys.stderr)
        return 2
    if args.max_items < 1 or args.delay < 0 or args.timeout <= 0:
        print("采集失败：max-items、delay、timeout 参数非法", file=sys.stderr)
        return 2

    capture_root = Path(args.capture_root)
    output_root = Path(args.output_root)
    token = load_or_create_token(capture_root, args.token)
    tasks = AutomationTaskStore()
    handler = make_handler(CaptureStore(capture_root, token), tasks)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    except OSError as exc:
        print(f"采集失败：无法启动本机控制服务（端口 {args.port}）：{exc}", file=sys.stderr)
        return 2
    thread = threading.Thread(target=server.serve_forever, name="keyword-capture-server", daemon=True)
    thread.start()
    search_url = args.search_url_template.replace("{keyword}", quote_plus(keyword))
    task = tasks.create(
        keyword,
        search_url=search_url,
        output_dir=output_root,
        max_items=args.max_items,
        delay_seconds=args.delay,
    )
    task_dir = output_root / task.id
    print(f"任务 {task.id} 已启动：{keyword}")
    print(f"请确认 Chrome 扩展已启用，接收地址为 http://127.0.0.1:{args.port}/captures")
    print(f"本机采集令牌：{token}")
    print("等待扩展自动搜索和采集……")
    try:
        try:
            finished = tasks.wait(task.id, timeout=args.timeout)
        except TimeoutError as exc:
            tasks.record_event(task.id, {"state": "failed", "message": str(exc)})
            finished = tasks.get(task.id)
        assert finished is not None
        inbox = task_dir / "inbox"
        records, failures, details = build_captures(inbox)
        task_dir.mkdir(parents=True, exist_ok=True)
        (task_dir / "task.json").write_text(
            json.dumps(finished.snapshot(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        output = task_dir / "product_snapshots.jsonl"
        markdown = task_dir / "review.md"
        errors = task_dir / "errors.jsonl"
        write_outputs(records, failures, details, output=output, markdown=markdown, errors=errors, raw_dir=task_dir / "raw")
        print(
            f"采集结束：状态 {finished.state}，发现 {finished.discovered}，"
            f"成功 {len(records)} 条，失败 {len(failures)} 条"
        )
        print(f"快照：{output}")
        print(f"审阅：{markdown}")
        print(f"错误：{errors}")
        return 0 if finished.state == "completed" and not failures else 1
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    values = list(argv) if argv is not None else sys.argv[1:]
    if values and values[0] == "browser":
        return browser_main(values[1:])
    args = build_parser().parse_args(argv)
    try:
        keywords = Path(args.keyword_file).read_text(encoding="utf-8").splitlines()
        provider = FixtureProvider(args.fixture) if args.fixture else HttpJsonProvider(args.api_base_url, os.getenv(args.api_token_env))
        config = CrawlConfig(args.per_keyword_limit, args.total_limit, args.page_size, args.delay, args.max_retries, 1.0, not args.no_raw)
        records, failures, raw_details = collect(keywords, provider, provider, config)
        write_outputs(records, failures, raw_details if config.keep_raw else [], output=args.output, markdown=args.markdown, errors=args.errors, raw_dir=args.raw_dir if config.keep_raw else None)
    except Exception as exc:  # CLI should return a useful error without a traceback by default
        print(f"采集失败：{exc}", file=sys.stderr)
        return 2
    print(f"采集完成：成功 {len(records)} 条，失败 {len(failures)} 条")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
