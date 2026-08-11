"""健康探针基类 + 探针结果结构。

每个模块实现一个探针，返回 ProbeResult。编排层据此驱动状态机：
  ok=True  -> record_success
  ok=False -> record_failure
status=SKIPPED（未配置凭证）不计入失败，避免没配 key 就把模块判死。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ProbeStatus(str, Enum):
    OK = "OK"            # 接通正常
    FAILED = "FAILED"    # 接口失效/被拒/异常（计入失败）
    SKIPPED = "SKIPPED"  # 未配置凭证，跳过（不计入失败）


@dataclass
class ProbeResult:
    module: str
    status: ProbeStatus
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status is ProbeStatus.OK

    @property
    def counts_as_failure(self) -> bool:
        return self.status is ProbeStatus.FAILED


class HealthProbe:
    """探针基类。子类实现 check() 返回 ProbeResult。"""

    module: str = "base"

    def check(self) -> ProbeResult:  # pragma: no cover - 抽象方法
        raise NotImplementedError

    def _ok(self, detail: str = "") -> ProbeResult:
        return ProbeResult(self.module, ProbeStatus.OK, detail)

    def _failed(self, detail: str = "") -> ProbeResult:
        return ProbeResult(self.module, ProbeStatus.FAILED, detail)

    def _skipped(self, detail: str = "") -> ProbeResult:
        return ProbeResult(self.module, ProbeStatus.SKIPPED, detail)
