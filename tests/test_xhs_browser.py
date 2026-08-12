import tempfile
import unittest
from pathlib import Path

from src.modules.promotion.publishing import prepare_xhs_browser
from src.modules.promotion.store import PromotionStore
from src.modules.promotion.xhs_browser import XHSBrowserConfig, XHSBrowserPublisher, _fill_script, browser_title


class FakePublisher:
    def __init__(self, output="READY_FOR_MANUAL_PUBLISH"):
        self.output = output
        self.calls = []

    def prepare(self, asset_dir, title, caption):
        self.calls.append((asset_dir, title, caption))
        return self.output


class TestXHSBrowser(unittest.TestCase):
    def test_title_removes_markdown(self):
        self.assertEqual(browser_title("这个 **好物** 也太香了"), "这个 好物 也太香了")

    def test_script_contains_upload_and_never_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            asset_dir = Path(tmp)
            (asset_dir / "cover.png").write_bytes(b"cover")
            (asset_dir / "content.png").write_bytes(b"content")
            script = _fill_script(asset_dir, "标题", "正文")
            self.assertIn("setInputFiles", script)
            self.assertIn("READY_FOR_MANUAL_PUBLISH", script)
            self.assertNotIn("click('发布", script)
            self.assertNotIn("发布笔记", script)

    def test_prepare_moves_delivery_to_manual_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "app.db")
            store = PromotionStore(db)
            content, _ = store.create(
                "2026-08-12", 7, {"title": "商品"},
                {"title": "**标题**", "xhs_caption": "正文"},
                {"title": "商品", "digest": "", "author": "", "content_html": "", "cover_image_path": "", "inline_image_paths": []},
            )
            asset_dir = Path(tmp) / "assets"
            asset_dir.mkdir()
            (asset_dir / "cover.png").write_bytes(b"cover")
            (asset_dir / "content.png").write_bytes(b"content")
            store.set_assets(content.id, str(asset_dir))
            self.assertTrue(store.approve(content.id))
            fake = FakePublisher()
            output = prepare_xhs_browser(store, content.id, fake)
            self.assertIn("READY", output)
            self.assertEqual(store.delivery(content.id, "xhs").status, "awaiting_manual_publish")
            self.assertEqual(fake.calls[0][1:], ("**标题**", "正文"))
            self.assertTrue(store.mark_xhs_published(content.id))
            self.assertEqual(store.delivery(content.id, "xhs").status, "published")

    def test_browser_config_uses_local_profile(self):
        config = XHSBrowserConfig.from_env("/tmp/project")
        self.assertEqual(config.profile_dir, "/tmp/project/.xhs-browser-profile")


if __name__ == "__main__":
    unittest.main()
