import importlib
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from src.modules.product_rag.manual_ingestion import ManualKnowledgeIngestionStore
from src.modules.promotion.store import PromotionStore
from src.modules.sourcing.platforms import PlatformPick, PlatformQuote
from src.modules.sourcing.store import SourcingPickStore
from src.modules.sourcing.types import SourcedItem


class TestConsoleKnowledgeDrafts(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module("scripts.run_console")
        self.db = str(Path(tempfile.mkdtemp()) / "console.db")
        self.store = SourcingPickStore(self.db)
        self.promotion_store = PromotionStore(self.db)
        self.knowledge_store = ManualKnowledgeIngestionStore(self.db)
        self.old_store, self.old_knowledge = self.module._store, self.module._knowledge_store
        self.old_promotion = self.module._promotion_store
        self.module._store, self.module._knowledge_store = self.store, self.knowledge_store
        self.module._promotion_store = self.promotion_store
        self.server = self.module.ThreadingHTTPServer(("127.0.0.1", 0), self.module.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        item = SourcedItem("supplier-1", "手机支架", 20, detail_url="https://supplier.example/items/1")
        quote = PlatformQuote("闲鱼", "¥", False, 39, 39, 10, 0.25)
        self.pick_id = self.store.save("2026-08-07", "手机支架", "domestic", PlatformPick(item, quote, score=80))

    def tearDown(self):
        self.server.shutdown()
        self.thread.join()
        self.module._store, self.module._knowledge_store = self.old_store, self.old_knowledge
        self.module._promotion_store = self.old_promotion

    def _post(self, path, body):
        request = urllib.request.Request(
            self.base + path, data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def _post_empty(self, path):
        request = urllib.request.Request(self.base + path, data=b"", method="POST")
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def _get(self, path):
        try:
            with urllib.request.urlopen(self.base + path) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_only_approved_pick_can_create_manual_draft(self):
        code, payload = self._post("/api/knowledge/drafts", {"pick_id": self.pick_id})
        self.assertEqual(code, 409)
        self.assertIn("已审核通过", payload["error"])
        self.assertEqual(self.knowledge_store.list_drafts(), [])

        self.assertTrue(self.store.approve(self.pick_id))
        code, payload = self._post("/api/knowledge/drafts", {"pick_id": self.pick_id})
        self.assertEqual(code, 201)
        self.assertEqual(payload["status"], "draft")
        self.assertEqual(self.knowledge_store.get(payload["id"]).status, "draft")

    def test_approved_pick_without_detail_url_can_use_list_data_only(self):
        item = SourcedItem("supplier-list-only", "列表商品", 20)
        quote = PlatformQuote("闲鱼", "¥", False, 39, 39, 10, 0.25)
        pick_id = self.store.save("2026-08-07", "验收", "domestic", PlatformPick(item, quote, score=80))
        self.assertTrue(self.store.approve(pick_id))

        code, payload = self._post("/api/knowledge/drafts", {"pick_id": pick_id})

        self.assertEqual(code, 201)
        self.assertEqual(payload["source_url"], f"https://sourcing.local/picks/{pick_id}")

    def test_promotion_approval_exposes_assets_and_waits_for_wechat_credentials(self):
        content, _ = self.promotion_store.create(
            "2026-08-11", self.pick_id,
            {"title": "手机支架", "price": 39},
            {"title": "手机支架", "xhs_caption": "正文"},
            {"title": "手机支架", "digest": "摘要", "author": "铺子",
             "content_html": "<p>正文</p>", "cover_image_path": "", "inline_image_paths": []},
        )
        asset_dir = Path(self.db).parent / "assets"
        asset_dir.mkdir()
        (asset_dir / "caption.txt").write_text("正文", encoding="utf-8")
        self.promotion_store.set_assets(content.id, str(asset_dir))

        code, payload = self._get("/api/promotions")
        self.assertEqual(code, 200)
        self.assertEqual(payload[0]["status"], "pending_review")

        code, payload = self._post_empty(f"/api/promotions/{content.id}/approve")
        self.assertEqual(code, 200)
        self.assertTrue(payload["ok"])
        self.assertIsNone(payload["wechat_media_id"])
        self.assertEqual(self.promotion_store.delivery(content.id, "xhs").status, "package_ready")

        request = urllib.request.urlopen(
            self.base + f"/api/promotions/{content.id}/assets/caption.txt"
        )
        self.assertEqual(request.read().decode("utf-8"), "正文")


if __name__ == "__main__":
    unittest.main()
