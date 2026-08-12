"""小红书独立入口：每日生成并交付人工发布包。"""
from __future__ import annotations

from .daily_job import run_daily_promotion


def run_daily_xhs(*args, **kwargs) -> dict:
    """生成小红书发布包；不会调用微信接口或任何公开发帖接口。"""
    return run_daily_promotion(*args, **kwargs)
