"""本机商品页面接收服务和 Chrome 自动采集任务控制，不连接闲鱼。"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import secrets
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .automation import AutomationTaskStore
from .redact import redact

MAX_BODY_BYTES = 512 * 1024


class CaptureStore:
    def __init__(self, output_dir: str | Path, token: str):
        self.output_dir = Path(output_dir)
        self.inbox_dir = self.output_dir / "inbox"
        self.token = token
        self._lock = threading.Lock()

    def save(self, payload: Any) -> Path:
        if not isinstance(payload, dict):
            raise ValueError("采集内容必须是 JSON object")
        source_url = payload.get("source_url")
        parsed = urlparse(source_url) if isinstance(source_url, str) else None
        if not parsed or parsed.scheme != "https" or not parsed.hostname or not parsed.hostname.endswith("goofish.com"):
            raise ValueError("只接受 goofish.com 的 https 商品页面")
        visible = payload.get("visible")
        if not isinstance(visible, dict) or not isinstance(visible.get("title"), str) or not visible["title"].strip():
            raise ValueError("采集内容缺少商品标题")
        item_id = _item_id(payload, source_url)
        safe = redact({
            "schema_version": 1,
            "source_url": source_url,
            "item_id_hint": item_id,
            "collected_at": payload.get("collected_at") or datetime.now(timezone.utc).isoformat(),
            "visible": visible,
        })
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        key = item_id if item_id != "unknown" else hashlib.sha256(source_url.encode("utf-8")).hexdigest()[:16]
        path = self.inbox_dir / f"item_{key}.json"
        with self._lock:
            self._remove_previous(source_url, item_id, keep=path)
            path.write_text(json.dumps(safe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    def _remove_previous(self, source_url: str, item_id: str, *, keep: Path) -> None:
        """兼容旧版时间戳文件，并清理同商品重复点击留下的文件。"""
        for candidate in self.inbox_dir.glob("*.json"):
            if candidate == keep:
                continue
            try:
                old = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            old_id = _item_id(old, old.get("source_url"))
            if (item_id != "unknown" and old_id == item_id) or (item_id == "unknown" and old.get("source_url") == source_url):
                candidate.unlink()


def _item_id(payload: dict[str, Any], source_url: Any) -> str:
    hint = str(payload.get("item_id_hint") or "").strip()
    if hint and all(char.isalnum() or char in "-_" for char in hint) and len(hint) <= 64:
        return hint
    if isinstance(source_url, str):
        parsed = urlparse(source_url)
        for key in ("itemId", "itemid", "id"):
            value = (parse_qs(parsed.query).get(key) or [""])[0]
            if value and all(char.isalnum() or char in "-_" for char in value) and len(value) <= 64:
                return value
    return "unknown"


def load_or_create_token(output_dir: str | Path, token: str | None = None) -> str:
    if token:
        return token
    path = Path(output_dir) / ".collector-token"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    path.parent.mkdir(parents=True, exist_ok=True)
    created = secrets.token_urlsafe(32)
    path.write_text(created + "\n", encoding="utf-8")
    path.chmod(0o600)
    return created


def make_handler(store: CaptureStore, tasks: AutomationTaskStore | None = None):
    class CaptureHandler(BaseHTTPRequestHandler):
        def _authorized(self) -> bool:
            return hmac.compare_digest(self.headers.get("X-Collector-Token", ""), store.token)

        def do_OPTIONS(self) -> None:  # noqa: N802
            self._respond(HTTPStatus.NO_CONTENT)

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path.rstrip("/")
            if path == "/captures" or path.startswith("/captures/"):
                if not self._authorized():
                    self._respond(HTTPStatus.UNAUTHORIZED, {"error": "invalid local collector token"})
                    return
                task_id = path.removeprefix("/captures/") if path != "/captures" else ""
                target_store = store
                if task_id:
                    if tasks is None:
                        self._respond(HTTPStatus.NOT_FOUND, {"error": "automation is not enabled"})
                        return
                    task = tasks.get(task_id)
                    if task is None:
                        self._respond(HTTPStatus.NOT_FOUND, {"error": "task not found"})
                        return
                    target_store = CaptureStore(Path(task.output_dir) / task.id, store.token)
                self._save_capture(target_store)
                return
            if path.startswith("/automation/tasks/") and path.endswith("/events"):
                if tasks is None:
                    self._respond(HTTPStatus.NOT_FOUND, {"error": "automation is not enabled"})
                    return
                if not self._authorized():
                    self._respond(HTTPStatus.UNAUTHORIZED, {"error": "invalid local collector token"})
                    return
                task_id = path.removeprefix("/automation/tasks/").removesuffix("/events").strip("/")
                try:
                    payload = self._read_json()
                    task = tasks.record_event(task_id, payload)
                except KeyError as exc:
                    self._respond(HTTPStatus.NOT_FOUND, {"error": str(exc)})
                    return
                except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                    self._respond(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                    return
                self._respond(HTTPStatus.OK, task.snapshot())
                return
            self._respond(HTTPStatus.NOT_FOUND, {"error": "not found"})

        def _save_capture(self, target_store: CaptureStore) -> None:
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_BODY_BYTES:
                    raise ValueError("请求体大小非法")
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                path = target_store.save(payload)
            except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                self._respond(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._respond(HTTPStatus.CREATED, {"ok": True, "file": path.name})

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_BODY_BYTES:
                raise ValueError("请求体大小非法")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("请求体必须是 JSON object")
            return payload

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path.rstrip("/")
            if path == "/automation/next":
                if tasks is None:
                    self._respond(HTTPStatus.NOT_FOUND, {"error": "automation is not enabled"})
                    return
                if not self._authorized():
                    self._respond(HTTPStatus.UNAUTHORIZED, {"error": "invalid local collector token"})
                    return
                task = tasks.claim_next()
                if task is None:
                    self._respond(HTTPStatus.NO_CONTENT)
                else:
                    self._respond(HTTPStatus.OK, task.snapshot())
                return
            if path.startswith("/automation/tasks/"):
                if tasks is None:
                    self._respond(HTTPStatus.NOT_FOUND, {"error": "automation is not enabled"})
                    return
                if not self._authorized():
                    self._respond(HTTPStatus.UNAUTHORIZED, {"error": "invalid local collector token"})
                    return
                task_id = path.removeprefix("/automation/tasks/").strip("/")
                task = tasks.get(task_id)
                if task is None:
                    self._respond(HTTPStatus.NOT_FOUND, {"error": "task not found"})
                else:
                    self._respond(HTTPStatus.OK, task.snapshot())
                return
            self._respond(HTTPStatus.NOT_FOUND, {"error": "not found"})

        def _respond(self, status: HTTPStatus, body: dict[str, Any] | None = None) -> None:
            encoded = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else b""
            self.send_response(status)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Collector-Token")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            if encoded:
                self.wfile.write(encoded)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return CaptureHandler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="商品页面本地采集接收服务")
    parser.add_argument("--output-dir", default="out/captures")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--token", help="可选固定令牌；默认首次运行时生成并存入 output-dir")
    args = parser.parse_args(argv)
    token = load_or_create_token(args.output_dir, args.token)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(CaptureStore(args.output_dir, token), AutomationTaskStore()))
    print(f"接收服务：http://127.0.0.1:{args.port}/captures")
    print(f"本机采集令牌：{token}")
    print("将令牌填入浏览器扩展设置；按 Ctrl+C 停止。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
