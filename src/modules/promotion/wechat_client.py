"""微信服务号草稿箱客户端。首期只创建草稿，不调用公开发布接口。"""
from __future__ import annotations

import json
import mimetypes
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Callable

from .types import WeChatArticle

_API_BASE = "https://api.weixin.qq.com"
Transport = Callable[[str, str, bytes | None, dict[str, str]], dict]


class WeChatAPIError(RuntimeError):
    pass


class WeChatClient:
    def __init__(self, app_id: str, app_secret: str, api_base: str = _API_BASE,
                 transport: Transport | None = None, now: Callable[[], float] = time.time):
        self.app_id = app_id
        self.app_secret = app_secret
        self.api_base = api_base.rstrip("/")
        self._transport = transport or self._http_transport
        self._now = now
        self._token: str | None = None
        self._token_expires_at = 0.0

    @property
    def available(self) -> bool:
        return bool(self.app_id and self.app_secret)

    def get_access_token(self) -> str:
        if not self.available:
            raise WeChatAPIError("未配置 WECHAT_APP_ID / WECHAT_APP_SECRET")
        if self._token and self._now() < self._token_expires_at:
            return self._token
        query = urllib.parse.urlencode({
            "grant_type": "client_credential", "appid": self.app_id, "secret": self.app_secret,
        })
        data = self._request("GET", f"/cgi-bin/token?{query}")
        token = str(data.get("access_token") or "")
        if not token:
            raise WeChatAPIError(self._error(data))
        self._token = token
        self._token_expires_at = self._now() + max(60, int(data.get("expires_in", 7200)) - 120)
        return token

    def create_draft(self, article: WeChatArticle) -> str:
        if not article.cover_image_path:
            raise WeChatAPIError("微信草稿需要至少一张封面图片")
        image_urls = [self.upload_article_image(path) for path in article.inline_image_paths]
        content = article.content_html
        for idx, image_url in enumerate(image_urls):
            content = content.replace(f"{{{{image:{idx}}}}}", image_url)
        media_id = self.upload_permanent_image(article.cover_image_path)
        payload = {"articles": [{
            "article_type": "news",
            "title": article.title[:32],
            "author": article.author[:16],
            "digest": article.digest[:120],
            "content": content,
            "thumb_media_id": media_id,
            "need_open_comment": 0,
            "only_fans_can_comment": 0,
        }]}
        data = self._request_json("POST", "/cgi-bin/draft/add", payload)
        draft_id = str(data.get("media_id") or "")
        if not draft_id:
            raise WeChatAPIError(self._error(data))
        return draft_id

    def upload_article_image(self, path: str) -> str:
        data = self._request_multipart("/cgi-bin/media/uploadimg", path)
        url = str(data.get("url") or "")
        if not url:
            raise WeChatAPIError(self._error(data))
        return url

    def upload_permanent_image(self, path: str) -> str:
        data = self._request_multipart("/cgi-bin/material/add_material?type=image", path)
        media_id = str(data.get("media_id") or "")
        if not media_id:
            raise WeChatAPIError(self._error(data))
        return media_id

    def _request_json(self, method: str, path: str, payload: dict) -> dict:
        return self._request(method, path, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                             {"Content-Type": "application/json; charset=utf-8"})

    def _request_multipart(self, path: str, file_path: str) -> dict:
        source = Path(file_path)
        if not source.is_file():
            raise WeChatAPIError(f"微信上传图片不存在：{source}")
        boundary = f"----promotion-{uuid.uuid4().hex}"
        mime = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        body = b"".join([
            f"--{boundary}\r\n".encode(),
            (f'Content-Disposition: form-data; name="media"; filename="{source.name}"\r\n'
             f"Content-Type: {mime}\r\n\r\n").encode(),
            source.read_bytes(), b"\r\n", f"--{boundary}--\r\n".encode(),
        ])
        return self._request("POST", path, body, {"Content-Type": f"multipart/form-data; boundary={boundary}"})

    def _request(self, method: str, path: str, body: bytes | None = None,
                 headers: dict[str, str] | None = None) -> dict:
        token = self.get_access_token() if not path.startswith("/cgi-bin/token") else ""
        separator = "&" if "?" in path else "?"
        url = f"{self.api_base}{path}{separator}access_token={urllib.parse.quote(token)}" if token else f"{self.api_base}{path}"
        data = self._transport(method, url, body, headers or {})
        if not isinstance(data, dict):
            raise WeChatAPIError("微信接口返回格式异常")
        if data.get("errcode") not in (None, 0):
            raise WeChatAPIError(self._error(data))
        return data

    @staticmethod
    def _error(data: dict) -> str:
        code = data.get("errcode")
        message = data.get("errmsg") or "微信接口调用失败"
        return f"微信接口错误 {code}: {message}" if code is not None else str(message)

    @staticmethod
    def _http_transport(method: str, url: str, body: bytes | None, headers: dict[str, str]) -> dict:
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                raw = response.read().decode("utf-8")
        except Exception as exc:  # noqa: BLE001
            raise WeChatAPIError(f"微信网络请求失败：{exc}") from exc
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise WeChatAPIError("微信接口返回非 JSON 内容") from exc
