"""推广模块（小红书/抖音）接通探针。

发帖走浏览器自动化（social-auto-upload / Playwright），封号风险次高。
本探针验证发布登录态 cookie 是否存在且站点可达。
  1. 两个平台都没配 cookie -> SKIPPED
  2. 配了任一平台 cookie，站点可达 -> OK；否则 FAILED
"""
from __future__ import annotations

from ..config import config
from ..core.health_probe import HealthProbe, ProbeResult

_XHS_HOST = "https://www.xiaohongshu.com"
_DOUYIN_HOST = "https://www.douyin.com"


class PromotionProbe(HealthProbe):
    module = "promotion"

    def check(self) -> ProbeResult:
        targets = []
        if config.XHS_COOKIE:
            targets.append(("小红书", _XHS_HOST, config.XHS_COOKIE))
        if config.DOUYIN_COOKIE:
            targets.append(("抖音", _DOUYIN_HOST, config.DOUYIN_COOKIE))

        if not targets:
            return self._skipped(
                "未配置 XHS_COOKIE / DOUYIN_COOKIE。需在对应平台网页端登录后取 cookie"
            )

        import urllib.request

        oks, fails = [], []
        for name, host, cookie in targets:
            try:
                req = urllib.request.Request(
                    host,
                    headers={"Cookie": cookie, "User-Agent": "Mozilla/5.0"},
                )
                with urllib.request.urlopen(req, timeout=8) as resp:
                    if resp.getcode() == 200:
                        oks.append(name)
                    else:
                        fails.append(f"{name}:HTTP{resp.getcode()}")
            except Exception as e:  # noqa: BLE001
                fails.append(f"{name}:{e}")

        if oks and not fails:
            return self._ok(f"发布登录态可用：{', '.join(oks)}")
        if oks and fails:
            return self._failed(f"部分可用 [{', '.join(oks)}]，异常 [{', '.join(fails)}]")
        return self._failed(f"全部异常：{', '.join(fails)}")
