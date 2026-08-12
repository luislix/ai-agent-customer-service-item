"""人工后台控制台：选品审核、推广内容和人工商品知识入库。

零依赖（标准库 http.server）。
    python -m scripts.run_console      # 打开 http://127.0.0.1:8000

API：GET /api/state、/api/stats、/api/picks?group=&status=、/api/promotions、/api/knowledge/drafts；
POST /api/picks/{id}/approve|reject、/api/promotions/{id}/xhs-prepare|xhs/published、
/api/knowledge/drafts、/api/knowledge/drafts/{id}/publish。
"""
from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import config  # noqa: E402
from src.modules.product_rag.factory import build_service  # noqa: E402
from src.modules.product_rag.manual_ingestion import (  # noqa: E402
    KnowledgeDraftInput,
    ManualKnowledgeIngestion,
    ManualKnowledgeIngestionStore,
)
from src.modules.sourcing.store import SourcingPickStore  # noqa: E402
from src.modules.promotion.publishing import prepare_xhs_browser, sync_wechat_draft  # noqa: E402
from src.modules.promotion.store import PromotionStore  # noqa: E402
from src.orchestrator import Orchestrator  # noqa: E402

_HTML = (Path(__file__).resolve().parent.parent / "src" / "console" / "index.html").read_text(encoding="utf-8")
_orch = Orchestrator()
_store = SourcingPickStore(config.DB_PATH)
_promotion_store = PromotionStore(config.DB_PATH)
_knowledge_store = ManualKnowledgeIngestionStore(config.DB_PATH)


def _knowledge_source_url(pick) -> str:
    """优先保留列表返回的来源链接；离线/列表缺失时指向本地选品记录。"""
    return pick.detail_url or f"https://sourcing.local/picks/{pick.id}"


def _promotion_json(content) -> dict:
    deliveries = {delivery.channel: delivery.__dict__ for delivery in _promotion_store.deliveries(content.id)}
    return {
        **content.__dict__, "deliveries": deliveries,
        "title": content.xhs_post.get("title", ""),
        "caption": content.xhs_post.get("xhs_caption", ""),
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # 安静
        pass

    def _send(self, code: int, body, ctype: str = "application/json") -> None:
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False))

    def _body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError) as exc:
            raise ValueError("请求体必须是 JSON object") from exc
        if not isinstance(payload, dict):
            raise ValueError("请求体必须是 JSON object")
        return payload

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/favicon.ico":
            return self._send(204, b"", "image/x-icon")
        if u.path in ("/", "/index.html"):
            return self._send(200, _HTML, "text/html")
        if u.path == "/api/state":
            return self._json(_orch.snapshot())
        if u.path == "/api/stats":
            return self._json(_store.stats())
        if u.path == "/api/picks":
            q = parse_qs(u.query)
            group = (q.get("group") or [None])[0]
            status = (q.get("status") or [None])[0]
            picks = _store.list_picks(status=status or None, group=group or None)
            return self._json([p.__dict__ for p in picks])
        if u.path == "/api/promotions":
            q = parse_qs(u.query)
            status = (q.get("status") or [None])[0]
            return self._json([_promotion_json(content) for content in _promotion_store.list(status or None)])
        if len(u.path.strip("/").split("/")) == 5:
            parts = u.path.strip("/").split("/")
            if parts[:2] == ["api", "promotions"] and parts[3] == "assets":
                try:
                    content_id = int(parts[2])
                    name = parts[4]
                    content = _promotion_store.get(content_id)
                    path = Path(content.asset_dir) / name if content else None
                    if not content or Path(name).name != name or not path.is_file():
                        return self._json({"error": "asset not found"}, 404)
                    ctype = "application/json" if name.endswith(".json") else "text/plain" if name.endswith(".txt") else "image/png"
                    return self._send(200, path.read_bytes(), ctype)
                except ValueError:
                    return self._json({"error": "bad id"}, 400)
        if u.path == "/api/knowledge/drafts":
            return self._json([draft.__dict__ for draft in _knowledge_store.list_drafts()])
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        parts = urlparse(self.path).path.strip("/").split("/")  # api/picks/{id}/{action}
        if len(parts) == 4 and parts[0] == "api" and parts[1] == "picks":
            try:
                pid = int(parts[2])
            except ValueError:
                return self._json({"error": "bad id"}, 400)
            action = parts[3]
            if action == "approve":
                return self._json({"ok": _store.approve(pid)})
            if action == "reject":
                return self._json({"ok": _store.reject(pid)})
            return self._json({"error": "bad action"}, 400)
        if len(parts) == 4 and parts[:2] == ["api", "promotions"]:
            try:
                content_id = int(parts[2])
            except ValueError:
                return self._json({"error": "bad id"}, 400)
            action = parts[3]
            if action == "approve":
                if not _promotion_store.approve(content_id):
                    return self._json({"error": "内容不存在或不在待审核状态"}, 409)
                try:
                    media_id = sync_wechat_draft(_promotion_store, content_id)
                except Exception as exc:  # noqa: BLE001
                    return self._json({"ok": True, "wechat_error": str(exc)})
                return self._json({"ok": True, "wechat_media_id": media_id})
            if action == "reject":
                return self._json({"ok": _promotion_store.reject(content_id)})
            if action == "xhs-prepare":
                try:
                    prepare_xhs_browser(_promotion_store, content_id)
                    return self._json({"ok": True, "status": "awaiting_manual_publish"})
                except (RuntimeError, ValueError) as exc:
                    return self._json({"error": str(exc)}, 422)
            return self._json({"error": "bad action"}, 400)
        if len(parts) == 5 and parts[:2] == ["api", "promotions"]:
            try:
                content_id = int(parts[2])
            except ValueError:
                return self._json({"error": "bad id"}, 400)
            if parts[3:] == ["wechat", "retry"]:
                try:
                    media_id = sync_wechat_draft(_promotion_store, content_id)
                    return self._json({"ok": True, "wechat_media_id": media_id})
                except (RuntimeError, ValueError) as exc:
                    return self._json({"error": str(exc)}, 422)
            if parts[3:] == ["xhs", "published"]:
                return self._json({"ok": _promotion_store.mark_xhs_published(content_id)})
        if parts == ["api", "knowledge", "drafts"]:
            try:
                payload = self._body()
                pick = _store.get_pick(int(payload.get("pick_id")))
                if pick is None:
                    return self._json({"error": "选品不存在"}, 404)
                if pick.status != "approved":
                    return self._json({"error": "只有已审核通过的选品可以创建知识库草稿"}, 409)
                draft = ManualKnowledgeIngestion(
                    _knowledge_store, _UnavailableImporter()
                ).create_draft(KnowledgeDraftInput(
                    source_pick_id=pick.id,
                    source_item_id=pick.item_id,
                    title=pick.title,
                    source_url=_knowledge_source_url(pick),
                    suggested_price=pick.resale_local,
                    currency="CNY" if pick.currency == "¥" else pick.currency,
                ))
                return self._json(draft.__dict__, 201)
            except (TypeError, ValueError) as exc:
                return self._json({"error": str(exc)}, 400)
        if len(parts) == 5 and parts[:3] == ["api", "knowledge", "drafts"] and parts[4] == "publish":
            try:
                draft_id = int(parts[3])
                payload = self._body()
                xianyu_item_id = str(payload.pop("xianyu_item_id", ""))
                importer = build_service()
                snapshot = ManualKnowledgeIngestion(_knowledge_store, importer).publish(
                    draft_id, xianyu_item_id, payload
                )
                return self._json(snapshot, 201)
            except (TypeError, ValueError, RuntimeError) as exc:
                return self._json({"error": str(exc)}, 422)
        self._json({"error": "not found"}, 404)


class _UnavailableImporter:
    """草稿创建不接触 RAG；该对象防止未来误把创建流程变成自动入库。"""

    def import_records(self, records):  # pragma: no cover - create_draft 不会调用
        raise RuntimeError("创建知识库草稿不会自动入库")


def main() -> int:
    host, port = "127.0.0.1", 8000
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"选品运营台 → http://{host}:{port}   (Ctrl+C 停止)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
