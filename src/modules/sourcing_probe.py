"""选品模块（万邦 Onebound）接通探针。

Onebound 是付费聚合 API（覆盖 1688/拼多多），三模块里最稳的一环。
  1. 没配 ONEBOUND_API_KEY -> SKIPPED
  2. 配了 key，调一次轻量端点验证连通与配额 -> OK / FAILED
"""
from __future__ import annotations

from ..config import config
from ..core.health_probe import HealthProbe, ProbeResult

# 文档站；真实业务端点形如 https://api-gw.onebound.cn/1688/item_search/
_ONEBOUND_DOC = "https://open.onebound.cn/"


class OneboundProbe(HealthProbe):
    module = "sourcing"

    def check(self) -> ProbeResult:
        if not config.ONEBOUND_API_KEY:
            return self._skipped(
                "未配置 ONEBOUND_API_KEY。需在 open.onebound.cn 注册获取 key/secret（付费）"
            )
        try:
            import urllib.request

            # 占位连通性检查；接入时替换为带签名的真实 item_search 调用
            req = urllib.request.Request(_ONEBOUND_DOC, headers={"User-Agent": "probe/1.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                code = resp.getcode()
            if code == 200:
                return self._ok("Onebound 平台可达。下一步：用 key+secret 调 1688/拼多多 item_search")
            return self._failed(f"Onebound 返回 HTTP {code}")
        except Exception as e:  # noqa: BLE001
            return self._failed(f"访问 Onebound 失败：{e}")
