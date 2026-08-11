"""授权数据源适配器。"""

from .base import DetailProvider, ProviderError, SearchProvider
from .fixture import FixtureProvider
from .http_json import HttpJsonProvider

__all__ = ["DetailProvider", "FixtureProvider", "HttpJsonProvider", "ProviderError", "SearchProvider"]
