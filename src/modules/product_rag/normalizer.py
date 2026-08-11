"""快照 canonical JSON 和版本哈希。"""
from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(payload: dict[str, Any]) -> str:
    stable = dict(payload)
    stable.pop("updated_at", None)
    return json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def snapshot_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
