"""编排层：把三模块的探针 <-> 状态机 <-> 工单 <-> 告警 串起来。

一个健康巡检周期 run_health_cycle()：
  对每个模块跑探针 -> 驱动状态机 -> 降级时建工单+告警。
这就是"单点失效不阻断全局 + 人工兜底 + 修复后转自动"的运行时落地。
"""
from __future__ import annotations

from dataclasses import dataclass

from .config import config
from .core.alert import send_alert
from .core.health_probe import HealthProbe, ProbeResult
from .core.state_machine import ModuleStateMachine
from .core.work_order import WorkOrderStore
from .modules.customer_probe import XianyuProbe
from .modules.promotion_probe import PromotionProbe
from .modules.sourcing_probe import OneboundProbe


@dataclass
class ModuleRuntime:
    sm: ModuleStateMachine
    probe: HealthProbe


class Orchestrator:
    def __init__(self, store: WorkOrderStore | None = None):
        self.store = store or WorkOrderStore(config.DB_PATH)
        self.modules: dict[str, ModuleRuntime] = {}
        self._register("customer", XianyuProbe())
        self._register("sourcing", OneboundProbe())
        self._register("promotion", PromotionProbe())

    def _register(self, name: str, probe: HealthProbe) -> None:
        sm = ModuleStateMachine(
            name=name,
            fail_threshold=config.HEALTH_FAIL_THRESHOLD,
            on_degrade=self._on_degrade,
            on_recover=self._on_recover,
        )
        self.modules[name] = ModuleRuntime(sm=sm, probe=probe)

    # ---- 降级/恢复回调 ----
    def _on_degrade(self, sm: ModuleStateMachine, reason: str) -> None:
        # 降级即建一条"模块掉线，待人工接管"的工单，并告警
        self.store.create(
            module=sm.name,
            action="module_degraded",
            payload={"reason": reason},
            reason=reason,
        )
        send_alert(
            f"模块[{sm.name}]已降级 AUTO->MANUAL，原因：{reason}。请人工接管，待修复后恢复。",
            webhook=config.ALERT_WEBHOOK,
        )

    def _on_recover(self, sm: ModuleStateMachine) -> None:
        send_alert(f"模块[{sm.name}]已恢复 MANUAL->AUTO。", webhook=config.ALERT_WEBHOOK)

    # ---- 巡检 ----
    def run_health_cycle(self) -> list[ProbeResult]:
        results = []
        for rt in self.modules.values():
            res = rt.probe.check()
            results.append(res)
            if res.counts_as_failure:
                rt.sm.record_failure(res.detail)
            elif res.ok:
                rt.sm.record_success()
            # SKIPPED：不计入成功也不计入失败，保持原状态
        return results

    # ---- 每日选品任务（带状态感知）----
    def run_sourcing_job(self, keywords: list[str], store=None, **kw) -> dict | None:
        """定时选品：sourcing 模块 AUTO 才跑，MANUAL（数据源降级/养号暂停）则跳过+告警。"""
        sm = self.modules["sourcing"].sm
        if not sm.is_auto:
            send_alert(
                f"选品模块处于 MANUAL（{sm.last_reason or '人工暂停'}），跳过本次定时选品。",
                webhook=config.ALERT_WEBHOOK,
            )
            return None
        from .modules.sourcing.daily_job import run_daily_sourcing
        from .modules.sourcing.store import SourcingPickStore
        store = store or SourcingPickStore(config.DB_PATH)
        return run_daily_sourcing(keywords, store, **kw)

    def run_promotion_job(self, sourcing_store=None, promotion_store=None, **kw) -> dict | None:
        """每日推广：推广模块 MANUAL 时入工单，AUTO 时生成待审核内容。"""
        sm = self.modules["promotion"].sm
        if not sm.is_auto:
            reason = sm.last_reason or "人工暂停"
            self.store.create(
                module="promotion", action="generate_daily_content",
                payload={"source_date": kw.get("source_date", "")}, reason=reason,
            )
            send_alert(
                f"推广模块处于 MANUAL（{reason}），每日内容已转人工处理。",
                webhook=config.ALERT_WEBHOOK,
            )
            return None
        from .modules.promotion.daily_job import run_daily_promotion
        from .modules.promotion.store import PromotionStore
        from .modules.sourcing.store import SourcingPickStore
        return run_daily_promotion(
            sourcing_store or SourcingPickStore(config.DB_PATH),
            promotion_store or PromotionStore(config.DB_PATH),
            **kw,
        )

    # ---- 人工后台用 ----
    def recover_module(self, name: str) -> bool:
        rt = self.modules.get(name)
        return bool(rt and rt.sm.recover(by="manual"))

    def snapshot(self) -> dict:
        return {
            "modules": {n: rt.sm.snapshot() for n, rt in self.modules.items()},
            "pending_work_orders": self.store.count_pending(),
        }
