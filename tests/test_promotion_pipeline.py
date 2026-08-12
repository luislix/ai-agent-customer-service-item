"""每日推广任务：选品快照、审批、发布包与渠道交付状态。"""
import json
import tempfile
import unittest
from pathlib import Path

from src.llm.placeholder import PlaceholderClient
from src.modules.promotion.daily_job import run_daily_promotion
from src.modules.promotion.publishing import sync_wechat_draft
from src.modules.promotion.store import PromotionStore
from src.modules.sourcing.platforms import PlatformPick, PlatformQuote
from src.modules.sourcing.store import SourcingPickStore
from src.modules.sourcing.types import SourcedItem


def _pick(item_id: str = "supplier-1") -> PlatformPick:
    item = SourcedItem(
        item_id=item_id,
        title="厂家直供 蓝牙耳机 全配件 现货",
        cost_price=20,
        sales=1200,
        pic_url="https://supplier.example/earphone.jpg",
        detail_url="https://supplier.example/items/1",
    )
    quote = PlatformQuote("闲鱼", "¥", False, 59.9, 59.9, 22, 0.36)
    return PlatformPick(item=item, best=quote, score=88, reason="销量可观，价格有优势")


def _render(post, out_dir: str, image_path: str = "") -> list[str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = [out / "cover.png", out / "content.png"]
    for path in paths:
        path.write_bytes(b"png")
    return [str(path) for path in paths]


class TestPromotionPipeline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "app.db")
        self.sourcing = SourcingPickStore(self.db)
        self.promotion = PromotionStore(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def _approved_pick(self, run_date: str = "2026-08-10") -> int:
        pick_id = self.sourcing.save(run_date, "蓝牙耳机", "domestic", _pick())
        self.assertTrue(self.sourcing.approve(pick_id))
        return pick_id

    def test_daily_job_uses_approved_snapshot_and_is_idempotent(self):
        pick_id = self._approved_pick()
        out_root = Path(self.tmp.name) / "promotion"
        result = run_daily_promotion(
            self.sourcing, self.promotion, run_date="2026-08-11",
            source_date="2026-08-10", output_root=str(out_root),
            llm=PlaceholderClient(), renderer=_render,
        )
        self.assertEqual(result["saved"], 1)
        content = self.promotion.get(result["content_id"])
        self.assertEqual(content.source_pick_id, pick_id)
        self.assertEqual(content.status, "pending_review")
        self.assertTrue(any(point.startswith("已售1200+") for point in content.source_snapshot["selling_points"]))
        self.assertEqual(content.source_snapshot["image_path"], "https://supplier.example/earphone.jpg")
        self.assertTrue((Path(content.asset_dir) / "caption.txt").exists())
        self.assertEqual(json.loads((Path(content.asset_dir) / "manifest.json").read_text(encoding="utf-8"))["caption"], content.xhs_post["xhs_caption"])

        duplicate = run_daily_promotion(
            self.sourcing, self.promotion, run_date="2026-08-11",
            source_date="2026-08-10", output_root=str(out_root),
            llm=PlaceholderClient(), renderer=_render,
        )
        self.assertEqual(duplicate["saved"], 0)
        self.assertEqual(self.promotion.count(), 1)

    def test_requires_review_before_channel_delivery(self):
        self._approved_pick()
        result = run_daily_promotion(
            self.sourcing, self.promotion, run_date="2026-08-11",
            source_date="2026-08-10", output_root=str(Path(self.tmp.name) / "promotion"),
            llm=PlaceholderClient(), renderer=_render,
        )
        content_id = result["content_id"]
        self.assertFalse(self.promotion.mark_xhs_published(content_id))
        self.assertTrue(self.promotion.approve(content_id))
        self.assertEqual(self.promotion.delivery(content_id, "xhs").status, "package_ready")
        self.assertTrue(self.promotion.mark_xhs_published(content_id))
        self.assertEqual(self.promotion.delivery(content_id, "xhs").status, "published")

    def test_no_approved_pick_skips_generation(self):
        self.sourcing.save("2026-08-10", "蓝牙耳机", "domestic", _pick())
        result = run_daily_promotion(
            self.sourcing, self.promotion, run_date="2026-08-11",
            source_date="2026-08-10", output_root=str(Path(self.tmp.name) / "promotion"),
            llm=PlaceholderClient(), renderer=_render,
        )
        self.assertEqual(result, {"saved": 0, "reason": "no_approved_pick"})

    def test_wechat_failure_is_persisted_for_retry(self):
        self._approved_pick()
        result = run_daily_promotion(
            self.sourcing, self.promotion, run_date="2026-08-11",
            source_date="2026-08-10", output_root=str(Path(self.tmp.name) / "promotion"),
            llm=PlaceholderClient(), renderer=_render,
        )
        self.assertTrue(self.promotion.approve(result["content_id"]))

        class FailingClient:
            available = True

            def create_draft(self, article):
                raise RuntimeError("wechat unavailable")

        with self.assertRaisesRegex(RuntimeError, "wechat unavailable"):
            sync_wechat_draft(self.promotion, result["content_id"], FailingClient())
        delivery = self.promotion.delivery(result["content_id"], "wechat")
        self.assertEqual(delivery.status, "failed")
        self.assertEqual(delivery.attempts, 1)

    def test_failed_render_can_be_retried(self):
        self._approved_pick()
        calls = {"count": 0}

        def renderer(post, out_dir, image_path=""):
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("browser unavailable")
            return _render(post, out_dir, image_path)

        args = dict(
            sourcing_store=self.sourcing, promotion_store=self.promotion,
            run_date="2026-08-11", source_date="2026-08-10",
            output_root=str(Path(self.tmp.name) / "promotion"),
            llm=PlaceholderClient(), renderer=renderer,
        )
        with self.assertRaisesRegex(RuntimeError, "browser unavailable"):
            run_daily_promotion(**args)
        retry = run_daily_promotion(**args)
        self.assertEqual(retry["saved"], 1)
        self.assertEqual(self.promotion.get(retry["content_id"]).status, "pending_review")


if __name__ == "__main__":
    unittest.main()
