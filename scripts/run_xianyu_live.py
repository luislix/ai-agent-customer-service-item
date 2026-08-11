"""闲鱼实时私信接入运行器（需在能访问 GitHub 的机器上、先装好 XianYuApis）。

默认自动回复真实消息；加 ``--dry-run`` 只收消息并生成 AI 草稿，不发送。

前置（本机）：
    git clone https://github.com/cv-cat/XianYuApis.git
    cd XianYuApis && pip install -r requirements.txt      # 另需 Node.js 18+
    # 把 XianYuApis 目录加入 PYTHONPATH，或与本项目放同级

用法：
    python -m scripts.run_xianyu_live              # 自动回复
    python -m scripts.run_xianyu_live --dry-run    # 只生成草稿（安全验证）
    python -m scripts.run_xianyu_live --live       # 自动回复（兼容旧参数）
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:  # noqa: BLE001
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import config  # noqa: E402
from src.core.alert import send_alert  # noqa: E402
from src.core.state_machine import ModuleStateMachine  # noqa: E402
from src.core.work_order import WorkOrderStore  # noqa: E402
from src.llm.factory import build_llm  # noqa: E402
from src.modules.customer.xianyu_live import XianyuLiveBridge  # noqa: E402
from src.modules.product_rag.factory import build_retriever  # noqa: E402

_SETUP_HINT = """
[未检测到 XianYuApis] 实时私信需要这个逆向协议库（本环境无法联网安装，请在你本机执行）：

    git clone https://github.com/cv-cat/XianYuApis.git
    cd XianYuApis
    pip install -r requirements.txt        # 另需安装 Node.js 18+（跑 JS 签名）

然后把 XianYuApis 加入 PYTHONPATH 后重跑本脚本。

接入点：XianYuApis 的 goofish_live 在收到买家消息时会回调一个"AI 回复函数"，
把它替换成本脚本里 bridge.handle_raw 即可（已自带：意图路由/议价/发货工单/降级兜底）。
"""


def _candidate_paths() -> list[Path]:
    """XianYuApis 的可能存放位置（按优先级）。"""
    root = Path(config.PROJECT_ROOT)
    paths = []
    if config.XIANYU_APIS_PATH:                       # .env 自定义
        paths.append(Path(config.XIANYU_APIS_PATH))
    paths.append(root / "vendor" / "XianYuApis")       # 推荐：项目内 vendor/
    paths.append(root.parent / "XianYuApis")           # 备选：与项目同级
    return paths


def _try_import_xianyu():
    """加入 sys.path 并 chdir 到 XianYuApis 目录后尝试导入；成功返回 True。

    XianYuApis 的 goofish_utils.py 用相对路径读 static/*.js（execjs 跑签名），
    必须在其自身目录下运行，故这里 chdir。我们自己的路径全用绝对路径，不受影响。
    """
    import os

    for p in _candidate_paths():
        if p.exists() and (p / "goofish_live.py").exists():
            sys.path.insert(0, str(p))
            os.chdir(p)
            break
    try:
        import goofish_live  # type: ignore  # noqa: F401
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[XianYuApis 导入失败] {e}")
        return False


def main() -> int:
    # 自动回复是默认行为；--dry-run 是明确的安全退回开关。
    dry_run = "--dry-run" in sys.argv
    live = not dry_run

    if not config.XIANYU_COOKIE:
        print("未配置 XIANYU_COOKIE，请先在 .env 填入闲鱼网页端 cookie。")
        return 1

    llm = build_llm()
    store = WorkOrderStore(config.DB_PATH)
    sm = ModuleStateMachine("customer")
    bridge = XianyuLiveBridge(llm, store, sm, dry_run=dry_run, retriever=build_retriever())

    print("=" * 64)
    print(f" 闲鱼实时私信接入  LLM={llm.name}  模式={'DRY-RUN(只收不发)' if dry_run else 'LIVE(真实发送)'}")
    print("=" * 64)
    if live:
        print("⚠️  自动回复已开启：将向真实买家发送 AI 回复，有封号风险，请先用小号验证。\n")

    if not _try_import_xianyu():
        print(_SETUP_HINT)
        print("\n[本地演示 bridge.handle_raw（不连接真实账号）]")
        demo = {"conversation_id": "demo1", "text": "能便宜点吗",
                "item_title": "iPhone 13 95新", "price": 2999, "floor_price": 2700}
        bridge.handle_raw(demo)
        return 2

    # 已装 XianYuApis：子类化其 XianyuLive，接入我们的 bridge
    import asyncio

    from src.modules.customer.xianyu_live_adapter import build_agent_live

    live_app = build_agent_live(config.XIANYU_COOKIE, bridge)

    # 启动前预检：调一次 get_token，识别风控/验证码/令牌过期，避免 XianYuApis 的 exit(0)
    print("启动前预检 get_token……")
    code, detail = _preflight_token(live_app)
    if code != "OK":
        sm.force_manual(detail)                 # 风控发生 -> 客服模块自动转人工兜底
        send_alert(f"闲鱼客服无法启动自动模式：{detail}。已转人工。", webhook=config.ALERT_WEBHOOK)
        print(f"\n[预检失败/{code}] {detail}")
        print(_RISK_HINT if code == "RISK" else "")
        print("客服模块已置为 MANUAL（人工兜底），解决后重跑即可恢复自动。")
        return 4

    print("预检通过，启动实时监听（Ctrl+C 退出）……\n")
    try:
        asyncio.run(live_app.main())
    except KeyboardInterrupt:
        print("\n已退出监听。")
    return 0


def _preflight_token(live_app) -> tuple[str, str]:
    """返回 (code, detail)。code: OK / RISK / EXPIRED / FAIL。"""
    try:
        res = live_app.xianyu.get_token()
    except Exception as e:  # noqa: BLE001
        return "FAIL", f"get_token 异常：{e}"
    ret = "".join(res.get("ret", [])) if isinstance(res, dict) else str(res)
    data = res.get("data", {}) if isinstance(res, dict) else {}
    if data.get("accessToken"):
        return "OK", "登录态有效，accessToken 获取成功"
    if "RGV587" in ret or "USER_VALIDATE" in ret or "captcha" in str(data).lower():
        return "RISK", f"触发闲鱼风控/验证码：{ret or data.get('url','')}"
    if "TOKEN_EXPIRED" in ret or "令牌过期" in ret:
        return "EXPIRED", "cookie 已过期（令牌过期），需重新在闲鱼网页端获取"
    return "FAIL", f"get_token 未返回 accessToken：{ret}"


_RISK_HINT = """
[闲鱼风控触发] 该账号/IP 被判定为机器行为，需要先解除：
  1. 用浏览器正常打开闲鱼、用此账号过掉滑块验证码，正常浏览几分钟（养号）
  2. 等待一段时间（建议数小时或隔天）让风控冷却
  3. 建议换干净小号 + 手机热点/换 IP，降低调用频率
  4. 解除后重新抓取新鲜 cookie 再跑
"""


if __name__ == "__main__":
    raise SystemExit(main())
