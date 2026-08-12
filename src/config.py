"""集中配置：从环境变量 / .env 读取，凭证后补也不影响脚手架运行。

设计：不依赖 python-dotenv，自带极简 .env 解析，缺失的凭证返回 None，
由各模块探针自行降级为 SKIPPED（未配置）而非报错。
"""
from __future__ import annotations

import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """把 .env 里的 KEY=VALUE 注入 os.environ（不覆盖已存在的真实环境变量）。"""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv(_PROJECT_ROOT / ".env")


def get(key: str, default: str | None = None) -> str | None:
    val = os.environ.get(key, default)
    return val if val else default


class Config:
    """全局配置访问点。新增凭证只需在这里加一个属性 + .env.example 补一行。"""

    PROJECT_ROOT = _PROJECT_ROOT

    # ---- 通用 ----
    DB_PATH = get("DB_PATH", str(_PROJECT_ROOT / "data" / "app.db"))
    HEALTH_FAIL_THRESHOLD = int(get("HEALTH_FAIL_THRESHOLD", "3"))

    # ---- 客服模块（闲鱼）----
    XIANYU_COOKIE = get("XIANYU_COOKIE")        # 网页端 F12 获取
    XIANYU_USER_ID = get("XIANYU_USER_ID")
    XIANYU_APIS_PATH = get("XIANYU_APIS_PATH")  # XianYuApis 库路径（留空则自动找 vendor/XianYuApis）
    # 拟人回复延迟（秒）：真人收到消息要读+打字，不会秒回。降低机器人特征。
    REPLY_DELAY_MIN = float(get("REPLY_DELAY_MIN", "3"))
    REPLY_DELAY_MAX = float(get("REPLY_DELAY_MAX", "12"))

    # ---- 选品模块 ----
    # 数据源：onebound（万邦，1000 起充）/ justoneapi（按次小额充值，token 走 query）
    SOURCING_PROVIDER = get("SOURCING_PROVIDER", "onebound")
    # 万邦 Onebound（1688/拼多多聚合）
    ONEBOUND_API_KEY = get("ONEBOUND_API_KEY")
    ONEBOUND_API_SECRET = get("ONEBOUND_API_SECRET")
    # justoneapi（多平台聚合，按次计费）。BASE 默认大陆专用 IP，海外可改 https://api.justoneapi.com
    JUSTONEAPI_TOKEN = get("JUSTONEAPI_TOKEN")
    JUSTONEAPI_BASE = get("JUSTONEAPI_BASE", "http://47.117.133.51:30015")
    # 跨境选品默认渠道（逗号分隔 key，见 platforms.PROFILES：tiktok_us/tiktok_uk/aliexpress）
    OVERSEAS_PLATFORMS = get("OVERSEAS_PLATFORMS", "tiktok_us,aliexpress")
    # 每日定时选品的关键词清单（逗号分隔）
    SOURCING_KEYWORDS = get("SOURCING_KEYWORDS", "手机支架,宠物玩具,厨房收纳")
    # 每日定时选品的运行时点（0-23 时），守护进程用
    SOURCING_RUN_HOUR = int(get("SOURCING_RUN_HOUR", "9"))

    # ---- 推广模块（小红书 / 抖音）----
    XHS_COOKIE = get("XHS_COOKIE")
    DOUYIN_COOKIE = get("DOUYIN_COOKIE")
    PROMOTION_RUN_HOUR = int(get("PROMOTION_RUN_HOUR", "10"))
    PROMOTION_TIMEZONE = get("PROMOTION_TIMEZONE", "Asia/Shanghai")
    WECHAT_APP_ID = get("WECHAT_APP_ID")
    WECHAT_APP_SECRET = get("WECHAT_APP_SECRET")

    # ---- LLM ----
    LLM_PROVIDER = get("LLM_PROVIDER", "qwen")   # qwen / deepseek / local
    QWEN_API_KEY = get("DASHSCOPE_API_KEY")      # 阿里云通义千问
    QWEN_MODEL = get("QWEN_MODEL", "qwen-plus")
    QWEN_ENDPOINT = get(
        "QWEN_ENDPOINT",
        "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
    )
    DEEPSEEK_API_KEY = get("DEEPSEEK_API_KEY")
    DEEPSEEK_MODEL = get("DEEPSEEK_MODEL", "deepseek-v4-flash")
    DEEPSEEK_ENDPOINT = get("DEEPSEEK_ENDPOINT", "https://api.deepseek.com/chat/completions")
    CLAUDE_API_KEY = get("ANTHROPIC_API_KEY")

    # ---- 商品 RAG（可选；未配置时使用 NullRetriever，不影响脚手架）----
    RAG_ENABLED = get("RAG_ENABLED", "false").lower() == "true"
    RAG_DATABASE_URL = get("RAG_DATABASE_URL")
    RAG_EMBEDDING_MODEL_PATH = get("RAG_EMBEDDING_MODEL_PATH", "BAAI/bge-m3")
    RAG_EMBEDDING_DEVICE = get("RAG_EMBEDDING_DEVICE", "auto")
    RAG_EMBEDDING_BATCH_SIZE = int(get("RAG_EMBEDDING_BATCH_SIZE", "16"))
    RAG_TOP_K = int(get("RAG_TOP_K", "5"))
    # bge-m3 本地 cosine 分数需按中文客服问法校准；低于 0.50 仍视为未命中。
    RAG_MIN_SCORE = float(get("RAG_MIN_SCORE", "0.50"))

    # ---- 告警 ----
    ALERT_WEBHOOK = get("ALERT_WEBHOOK")          # 飞书/钉钉/企微机器人


config = Config()
