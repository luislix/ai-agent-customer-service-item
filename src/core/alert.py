"""告警通道：模块降级时推送到飞书/钉钉/企微机器人。

未配置 webhook 时退化为控制台打印，保证脚手架可跑。
"""
from __future__ import annotations

import json
import urllib.request


def send_alert(text: str, webhook: str | None = None) -> None:
    line = f"[ALERT] {text}"
    print(line)
    if not webhook:
        return
    try:
        # 飞书自定义机器人格式；钉钉/企微可在此分支适配
        data = json.dumps({"msg_type": "text", "content": {"text": text}}).encode("utf-8")
        req = urllib.request.Request(
            webhook, data=data, headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:  # noqa: BLE001 告警失败不应阻断主流程
        print(f"[ALERT] webhook 推送失败（不影响主流程）: {e}")
