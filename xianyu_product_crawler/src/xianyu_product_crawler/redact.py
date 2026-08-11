from __future__ import annotations

import re
from typing import Any

_SECRET = re.compile(r"(?i)(cookie|token|authorization|set-cookie|device[_-]?id|password|手机号|手机|电话|地址)")
_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")


def redact(value: Any, *, key: str = "") -> Any:
    if _SECRET.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): redact(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(item, key=key) for item in value]
    if isinstance(value, str):
        return _PHONE.sub("[REDACTED_PHONE]", value)
    return value
