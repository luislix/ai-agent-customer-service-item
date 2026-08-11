"""Phase 0 接通体检：一键跑三模块探针，输出"今天能否接通"报告。

用法（项目根目录下）：
    python -m scripts.run_phase0_check
没配凭证时各模块显示 SKIPPED 并给出补齐指引，脚手架本身可空跑验证。
"""
from __future__ import annotations

import sys
from pathlib import Path

# Windows 控制台默认 GBK，强制 UTF-8 输出避免中文乱码
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:  # noqa: BLE001
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.health_probe import ProbeStatus  # noqa: E402
from src.orchestrator import Orchestrator  # noqa: E402

_ICON = {ProbeStatus.OK: "[OK ]", ProbeStatus.FAILED: "[FAIL]", ProbeStatus.SKIPPED: "[SKIP]"}
_CN = {"customer": "客服(闲鱼)", "sourcing": "选品(1688/PDD)", "promotion": "推广(小红书/抖音)"}


def main() -> int:
    print("=" * 64)
    print(" Phase 0 接通体检 —— 闲鱼智能客服 AI Agent")
    print("=" * 64)

    orch = Orchestrator()
    results = orch.run_health_cycle()

    for r in results:
        name = _CN.get(r.module, r.module)
        print(f"\n{_ICON[r.status]} {name}")
        print(f"      {r.detail}")

    snap = orch.snapshot()
    print("\n" + "-" * 64)
    print(" 模块状态汇总：")
    for name, m in snap["modules"].items():
        print(f"   - {_CN.get(name, name):<22} 状态={m['state']:<7} 健康={m['healthy']}")
    print(f" 待处理工单数：{snap['pending_work_orders']}")
    print("-" * 64)

    failed = [r for r in results if r.status is ProbeStatus.FAILED]
    skipped = [r for r in results if r.status is ProbeStatus.SKIPPED]
    if skipped:
        print(f"\n提示：{len(skipped)} 个模块未配置凭证（SKIP），补齐 .env 后重跑即可实测。")
    if failed:
        print(f"警告：{len(failed)} 个模块接通失败，需排查后再进入 Phase 1。")
        return 1
    print("\n体检完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
