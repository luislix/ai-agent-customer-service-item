"""推广模块离线测试：文案降级、HTML 填充、高亮转换（不需要 playwright/LLM）。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.llm.placeholder import PlaceholderClient  # noqa: E402
from src.modules.promotion.card_renderer import (  # noqa: E402
    _bold, _ensure_local_image, _hl, build_content_html, build_cover_html,
)
from src.modules.promotion.copywriter import write_post  # noqa: E402
from src.modules.promotion.types import Product, PromoPost  # noqa: E402

SAMPLE = Product(title="索尼降噪耳机 95新", price=899, category="数码好物",
                 selling_points=["旗舰降噪", "95新", "配件全"])


class TestCopywriter(unittest.TestCase):
    def test_fallback_post_valid(self):
        post = write_post(SAMPLE, PlaceholderClient(), index="03")
        self.assertIsInstance(post, PromoPost)
        self.assertEqual(post.index, "03")
        self.assertEqual(post.price, "899")
        self.assertEqual(len(post.cover_points), 3)
        self.assertTrue(post.xhs_caption)
        self.assertIn("#", post.xhs_caption)          # 带话题标签

    def test_fallback_uses_known_points(self):
        post = write_post(SAMPLE, PlaceholderClient())
        self.assertIn("旗舰降噪", post.cover_points)

    def test_english_fallback_post(self):
        post = write_post(SAMPLE, PlaceholderClient(), index="02", locale="en")
        self.assertIsInstance(post, PromoPost)
        self.assertEqual(post.index, "02")
        # 英文 caption 带 TikTok 风格 hashtag
        self.assertIn("#", post.xhs_caption)
        self.assertTrue(any(c.isascii() and c.isalpha() for c in post.title))
        self.assertIn("#tiktokmademebuyit", post.xhs_caption)


class TestHighlight(unittest.TestCase):
    def test_hl_converts_and_escapes(self):
        out = _hl("超值 **好物** <hack>")
        self.assertIn('<span class="hl">好物</span>', out)
        self.assertIn("&lt;hack&gt;", out)            # XSS 转义

    def test_bold_converts(self):
        self.assertIn("<b>¥899</b>", _bold("到手 **¥899** 啦"))


class TestHtmlBuild(unittest.TestCase):
    def setUp(self):
        self.post = write_post(SAMPLE, PlaceholderClient(), index="01")

    def test_cover_html_has_content(self):
        h = build_cover_html(self.post)
        self.assertIn("数码好物", h)                   # kicker
        self.assertIn("899", h)                        # price
        self.assertIn('class="hl"', h)                 # 标题高亮已渲染
        self.assertNotIn("{{", h)                      # 占位符全部替换

    def test_content_html_has_items(self):
        h = build_content_html(self.post)
        self.assertIn("旗舰降噪", h)
        self.assertNotIn("{{", h)
        self.assertEqual(h.count('class="item"'), len(self.post.content_items))


class TestEnsureLocalImage(unittest.TestCase):
    def test_passthrough_local_and_empty(self):
        import tempfile
        out = Path(tempfile.mkdtemp())
        self.assertEqual(_ensure_local_image("", out), "")
        self.assertEqual(_ensure_local_image("/local/x.jpg", out), "/local/x.jpg")
        # 远程下载失败时回退空串（无效域名，不依赖外网成功）
        self.assertEqual(_ensure_local_image("http://nonexistent.invalid/x.jpg", out), "")


if __name__ == "__main__":
    unittest.main()
