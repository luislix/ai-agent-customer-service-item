"""微信草稿客户端：token 缓存、素材上传、草稿错误不吞没。"""
import json
import tempfile
import unittest
from pathlib import Path

from src.modules.promotion.types import WeChatArticle
from src.modules.promotion.wechat_client import WeChatClient, WeChatAPIError


class FakeTransport:
    def __init__(self):
        self.calls = []

    def __call__(self, method, url, body, headers):
        self.calls.append((method, url, body, headers))
        if "/cgi-bin/token?" in url:
            return {"access_token": "token-1", "expires_in": 7200}
        if "uploadimg" in url:
            return {"url": "https://mmbiz.example/inline.jpg"}
        if "add_material" in url:
            return {"media_id": "cover-media"}
        if "draft/add" in url:
            return {"media_id": "draft-media"}
        raise AssertionError(url)


class TestWeChatClient(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cover = Path(self.tmp.name) / "cover.png"
        self.content = Path(self.tmp.name) / "content.png"
        self.cover.write_bytes(b"cover")
        self.content.write_bytes(b"content")

    def tearDown(self):
        self.tmp.cleanup()

    def test_creates_draft_and_reuses_token(self):
        transport = FakeTransport()
        client = WeChatClient("app-id", "app-secret", transport=transport)
        article = WeChatArticle(
            title="每日好物", digest="一条摘要", author="闲鱼好物铺",
            content_html='<p>正文</p><img src="{{image:0}}">',
            cover_image_path=str(self.cover), inline_image_paths=[str(self.content)],
        )
        self.assertEqual(client.create_draft(article), "draft-media")
        self.assertEqual(client.create_draft(article), "draft-media")
        token_calls = [call for call in transport.calls if "/cgi-bin/token?" in call[1]]
        self.assertEqual(len(token_calls), 1)
        draft_call = [call for call in transport.calls if "draft/add" in call[1]][0]
        payload = json.loads(draft_call[2].decode("utf-8"))
        self.assertIn("https://mmbiz.example/inline.jpg", payload["articles"][0]["content"])
        self.assertEqual(payload["articles"][0]["thumb_media_id"], "cover-media")

    def test_api_error_is_exposed_without_credentials(self):
        client = WeChatClient("", "")
        with self.assertRaises(WeChatAPIError):
            client.get_access_token()


if __name__ == "__main__":
    unittest.main()
