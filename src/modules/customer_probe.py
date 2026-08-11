"""客服模块（闲鱼）接通探针 —— Phase 0 最高优先级验证。

闲鱼私信走逆向协议（参考 cv-cat/XianYuApis：mtop h5 sign 签名 + WebSocket + Protobuf），
是整个系统最易失效的一环。本探针做"今天登录态是否真有效"的硬验证：

  1. 没配 XIANYU_COOKIE                 -> SKIPPED
  2. cookie 形态异常                    -> FAILED
  3. 发一个带 h5 签名的真实 mtop 请求：
       ret=SUCCESS                      -> OK（登录态有效，私信签名机制可用）
       令牌过期/FAIL_SYS_TOKEN_EXPIRED  -> FAILED（cookie 过期，需重新获取）
       限流/RGV587/被风控               -> FAILED
       其它                             -> FAILED（带原始 ret 便于排查）

h5 sign 算法：md5(token & timestamp & appKey & data)，token 取自 _m_h5_tk 下划线前段。
这与 XianYuApis 收发私信用的是同一套签名机制，故本探针能真实反映私信链路可用性。
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.parse
import urllib.request

from ..config import config
from ..core.health_probe import HealthProbe, ProbeResult

_APP_KEY = "34839810"  # 闲鱼(goofish) h5 appKey
_API = "mtop.taobao.idlemtopsearch.pc.search"
_ENDPOINT = f"https://h5api.m.goofish.com/h5/{_API}/1.0/"


def _ck(cookie: str, name: str) -> str | None:
    m = re.search(rf"{name}=([^;]+)", cookie)
    return m.group(1) if m else None


class XianyuProbe(HealthProbe):
    module = "customer"

    def check(self) -> ProbeResult:
        cookie = config.XIANYU_COOKIE
        if not cookie:
            return self._skipped(
                "未配置 XIANYU_COOKIE。请在闲鱼网页端(goofish.com)登录后 F12 复制 cookie 到 .env"
            )

        m_h5_tk = _ck(cookie, "_m_h5_tk")
        if not m_h5_tk or not _ck(cookie, "cookie2"):
            return self._failed(
                "XIANYU_COOKIE 形态异常（缺少 _m_h5_tk / cookie2），可能复制不全或已过期"
            )

        token = m_h5_tk.split("_")[0]
        data = json.dumps(
            {"pageNumber": 1, "keyword": "测试", "fromFilter": False,
             "rowsPerPage": 1, "bizFrom": "home"},
            ensure_ascii=False,
        )
        t = str(int(time.time() * 1000))
        sign = hashlib.md5(f"{token}&{t}&{_APP_KEY}&{data}".encode("utf-8")).hexdigest()
        params = {
            "jsv": "2.7.2", "appKey": _APP_KEY, "t": t, "sign": sign,
            "api": _API, "v": "1.0", "type": "json", "dataType": "json",
            "sessionOption": "AutoLoginOnly", "data": data,
        }
        url = _ENDPOINT + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(
            url,
            headers={
                "Cookie": cookie,
                "Referer": "https://www.goofish.com/",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                ),
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                body = resp.read().decode("utf-8", "ignore")
        except Exception as e:  # noqa: BLE001
            return self._failed(f"mtop 请求失败（网络/风控）：{e}")

        try:
            ret = "".join(json.loads(body).get("ret", []))
        except Exception:  # noqa: BLE001
            return self._failed(f"mtop 返回非预期内容：{body[:120]}")

        nick = urllib.parse.unquote(_ck(cookie, "tracknick") or "")
        unb = _ck(cookie, "unb") or ""
        if "SUCCESS" in ret:
            return self._ok(f"登录态有效（用户 {nick} / unb={unb}），h5 签名机制可用，私信链路具备接入条件")
        if "TOKEN_EXPIRED" in ret or "令牌过期" in ret:
            return self._failed("cookie 已过期（令牌过期），需重新在网页端获取 _m_h5_tk")
        if "RGV587" in ret or "限流" in ret or "FLOW" in ret:
            return self._failed(f"被风控/限流：{ret}")
        return self._failed(f"mtop 调用未成功：{ret}")
