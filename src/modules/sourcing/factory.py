"""按配置选择选品数据源。新增数据源只需在这里加一支。

SOURCING_PROVIDER=onebound（默认）/ justoneapi
任一 client 都实现 .search(query)->list[SourcedItem] 与 .available，可被 SourcingAgent 直接替换。
"""
from __future__ import annotations

from ...config import config
from .justoneapi_client import JustOneApiClient
from .onebound_client import OneboundClient


def make_sourcing_client():
    """根据 SOURCING_PROVIDER 返回对应数据源 client。"""
    if (config.SOURCING_PROVIDER or "").lower() == "justoneapi":
        return JustOneApiClient()
    return OneboundClient()
