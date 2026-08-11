"""状态机核心逻辑测试：降级、工单兜底、人工恢复、自动恢复。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.state_machine import ModuleState, ModuleStateMachine  # noqa: E402


class TestStateMachine(unittest.TestCase):
    def test_degrade_after_threshold(self):
        degraded = []
        sm = ModuleStateMachine("customer", fail_threshold=3,
                                on_degrade=lambda s, r: degraded.append(r))
        sm.record_failure("e1")
        sm.record_failure("e2")
        self.assertIs(sm.state, ModuleState.AUTO)   # 还没到阈值
        sm.record_failure("e3")
        self.assertIs(sm.state, ModuleState.MANUAL)  # 第3次降级
        self.assertEqual(degraded, ["e3"])

    def test_success_resets_failures(self):
        sm = ModuleStateMachine("x", fail_threshold=3)
        sm.record_failure()
        sm.record_failure()
        sm.record_success()                          # 中途恢复，计数清零
        sm.record_failure()
        sm.record_failure()
        self.assertIs(sm.state, ModuleState.AUTO)    # 不会因累计而误降级

    def test_manual_recover_requires_healthy(self):
        sm = ModuleStateMachine("x", fail_threshold=1)
        sm.record_failure("down")
        self.assertIs(sm.state, ModuleState.MANUAL)
        self.assertFalse(sm.recover(by="manual"))    # 探针还没好，不许回切
        sm.record_success()                          # 探针恢复（healthy=True）
        self.assertTrue(sm.recover(by="manual"))     # 现在可以人工恢复
        self.assertIs(sm.state, ModuleState.AUTO)

    def test_auto_recover(self):
        sm = ModuleStateMachine("x", fail_threshold=1, auto_recover=True)
        sm.record_failure("down")
        self.assertIs(sm.state, ModuleState.MANUAL)
        sm.record_success()                          # 自动回切
        self.assertIs(sm.state, ModuleState.AUTO)

    def test_force_manual(self):
        sm = ModuleStateMachine("x")
        sm.force_manual("养号暂停")
        self.assertIs(sm.state, ModuleState.MANUAL)


if __name__ == "__main__":
    unittest.main()
