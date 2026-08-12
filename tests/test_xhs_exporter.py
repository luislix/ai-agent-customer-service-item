"""小红书发布包的可审计文件清单。"""
import json
import tempfile
import unittest
from pathlib import Path

from src.modules.promotion.types import Product, PromoPost
from src.modules.promotion.xhs_exporter import export_package


class TestXhsExporter(unittest.TestCase):
    def test_manifest_contains_channel_title_hashes_and_source(self):
        post = PromoPost(
            kicker="数码", index="01", title="**好物**", subtitle="值得买",
            price="39", cover_points=["轻便"], content_eyebrow="推荐理由",
            content_heading="为什么值得买", content_items=[{"lead": "轻便", "desc": "日常好用"}],
            callout="带走它", xhs_caption="正文 #好物",
        )
        with tempfile.TemporaryDirectory() as tmp:
            cover = Path(tmp) / "cover.png"
            content = Path(tmp) / "content.png"
            cover.write_bytes(b"cover")
            content.write_bytes(b"content")
            out = Path(tmp) / "package"
            export_package(post, [str(cover), str(content)], str(out), {"pick_id": 7})
            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["channel"], "xiaohongshu")
            self.assertEqual(manifest["title"], "**好物**")
            self.assertEqual(manifest["source"]["pick_id"], 7)
            self.assertEqual(len(manifest["images"]), 2)
            self.assertTrue(manifest["images"][0]["sha256"])
            self.assertTrue((out / "cover.png").is_file())
            self.assertTrue((out / "content.png").is_file())

    def test_missing_image_is_rejected(self):
        post = PromoPost(
            kicker="好物", index="01", title="标题", subtitle="副标题", price="1",
            cover_points=[], content_eyebrow="", content_heading="", content_items=[],
            callout="", xhs_caption="正文",
        )
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                export_package(post, [str(Path(tmp) / "missing.png")], tmp, {})


if __name__ == "__main__":
    unittest.main()
