"""客服模块端到端模拟：喂一组买家消息，看 Agent 拟人回复 + 动作 + 工单兜底。

用法（项目根目录）：
    python -m scripts.run_customer_sim
没配 DASHSCOPE_API_KEY 时用占位回复，仍可完整跑通流程；配了 key 则为真实通义千问回复。
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
from src.core.state_machine import ModuleStateMachine  # noqa: E402
from src.core.work_order import WorkOrderStore  # noqa: E402
from src.llm.factory import build_llm  # noqa: E402
from src.modules.customer.channel import SimulatedChannel  # noqa: E402
from src.modules.customer.dispatcher import CustomerDispatcher  # noqa: E402
from src.modules.customer.types import BuyerMessage  # noqa: E402
from src.modules.product_rag.factory import build_retriever  # noqa: E402

ITEM = dict(item_id="A1", item_title="iPhone 13 128G 国行 95新",
            item_price=2999.0, floor_price=2700.0)

SCENARIOS = [
    BuyerMessage("c1", "b1", "在吗？", **ITEM),
    BuyerMessage("c2", "b2", "这个能便宜点吗，2500 行不行", **ITEM),
    BuyerMessage("c2", "b2", "再便宜点呗，诚心要", **ITEM),
    BuyerMessage("c3", "b3", "成色怎么样？有没有划痕", **ITEM),
    BuyerMessage("c4", "b4", "什么时候发货？", **ITEM),
    BuyerMessage("c5", "b5", "我已经拍下付款了", paid=True, **ITEM),
    BuyerMessage("c6", "b6", "收到货屏幕有问题，要退货", **ITEM),
]


def main() -> int:
    llm = build_llm()
    db = str(Path(config.PROJECT_ROOT) / "data" / "sim.db")
    Path(db).unlink(missing_ok=True)
    store = WorkOrderStore(db)
    sm = ModuleStateMachine("customer")

    print("=" * 64)
    print(f" 客服模块端到端模拟  (LLM: {llm.name}{'（真实）' if llm.name!='placeholder' else '（占位，未配key）'})")
    print("=" * 64)

    ch = SimulatedChannel(list(SCENARIOS))
    dispatcher = CustomerDispatcher(ch, llm, store, sm, retriever=build_retriever())
    trace = dispatcher.run_once()

    for t in trace:
        print(f"\n[会话 {t['conversation']}] 意图={t.get('intent','-')}  动作={t.get('actions',[])}")
        print(f"  AI回复: {t.get('reply','')}")

    print("\n" + "-" * 64)
    print(" 演示模块降级 -> 人工兜底：把客服模块切到 MANUAL，再来一条消息")
    sm.force_manual("模拟协议失效")
    ch.push(BuyerMessage("c7", "b7", "这个还在吗", **ITEM))
    trace2 = dispatcher.run_once()
    for t in trace2:
        print(f"  [会话 {t['conversation']}] 处理方式={t['handled']}  -> 工单#{t.get('work_order')}")

    print("\n" + "-" * 64)
    print(" 工单汇总（人工后台待处理）：")
    for wo in store.list_pending("customer"):
        print(f"   #{wo.id} [{wo.action}] {wo.reason}  payload={wo.payload}")
    print("-" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
