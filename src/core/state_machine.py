"""模块状态机：AUTO <-> MANUAL 自动降级与恢复。

这是"单点失效不阻断全局 + 人工兜底 + 修复后转自动"的核心实现。
- 健康探针连续失败 N 次 -> 自动切 MANUAL，触发 on_degrade（建工单 + 告警）。
- 探针恢复后：默认需人工确认才回 AUTO（auto_recover=False，更安全）；
  也可设 auto_recover=True 让其探针一好就自动回 AUTO。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


class ModuleState(str, Enum):
    AUTO = "AUTO"        # 全自动执行
    MANUAL = "MANUAL"    # 自动暂停，转人工接管


@dataclass
class ModuleStateMachine:
    name: str
    fail_threshold: int = 3
    auto_recover: bool = False
    state: ModuleState = ModuleState.AUTO
    consecutive_failures: int = 0
    healthy: bool = True
    # 回调：降级/恢复时触发（用于建工单、发告警、写日志）
    on_degrade: Callable[["ModuleStateMachine", str], None] | None = None
    on_recover: Callable[["ModuleStateMachine"], None] | None = None
    last_reason: str = ""
    _history: list[str] = field(default_factory=list)

    # ---- 探针结果驱动 ----
    def record_success(self) -> None:
        self.consecutive_failures = 0
        self.healthy = True
        if self.state is ModuleState.MANUAL and self.auto_recover:
            self.recover(by="auto")

    def record_failure(self, reason: str = "") -> None:
        self.consecutive_failures += 1
        self.healthy = False
        self.last_reason = reason
        if (
            self.state is ModuleState.AUTO
            and self.consecutive_failures >= self.fail_threshold
        ):
            self._degrade(reason)

    # ---- 状态流转 ----
    def _degrade(self, reason: str) -> None:
        self.state = ModuleState.MANUAL
        self._history.append(f"AUTO->MANUAL ({reason})")
        if self.on_degrade:
            self.on_degrade(self, reason)

    def recover(self, by: str = "manual") -> bool:
        """从 MANUAL 回到 AUTO。人工恢复要求探针当前健康，避免反复横跳。"""
        if self.state is not ModuleState.MANUAL:
            return False
        if by == "manual" and not self.healthy:
            return False  # 探针还没好，不允许人工强切（可加 force 参数另说）
        self.state = ModuleState.AUTO
        self.consecutive_failures = 0
        self._history.append(f"MANUAL->AUTO (by {by})")
        if self.on_recover:
            self.on_recover(self)
        return True

    def force_manual(self, reason: str = "manual_pause") -> None:
        """人工主动暂停某模块（如怀疑风控、要养号），不依赖探针失败。"""
        if self.state is ModuleState.AUTO:
            self._degrade(reason)

    @property
    def is_auto(self) -> bool:
        return self.state is ModuleState.AUTO

    def snapshot(self) -> dict:
        return {
            "name": self.name,
            "state": self.state.value,
            "healthy": self.healthy,
            "consecutive_failures": self.consecutive_failures,
            "last_reason": self.last_reason,
            "history": list(self._history),
        }
