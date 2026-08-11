"""平台参数外部校准测试：JSON 覆盖默认参数、缺文件/坏格式静默跳过（不需网络）。"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.modules.sourcing.platforms import PROFILES, _apply_overrides  # noqa: E402


class TestOverrides(unittest.TestCase):
    def _copy(self):
        return dict(PROFILES)   # 浅拷贝，值为 frozen dataclass，replace 生成新对象

    def test_json_overrides_allowed_fields(self):
        tmp = Path(tempfile.mkdtemp()) / "p.json"
        tmp.write_text(json.dumps({
            "tiktok_us": {"commission_rate": 0.12, "fulfillment_rmb": 40, "_note": "忽略"},
        }), encoding="utf-8")
        out = _apply_overrides(self._copy(), tmp)
        self.assertEqual(out["tiktok_us"].commission_rate, 0.12)
        self.assertEqual(out["tiktok_us"].fulfillment_rmb, 40.0)
        # 全局 PROFILES 不被污染
        self.assertEqual(PROFILES["tiktok_us"].commission_rate, 0.06)

    def test_missing_file_is_noop(self):
        out = _apply_overrides(self._copy(), Path("nope_does_not_exist.json"))
        self.assertEqual(out["tiktok_us"].commission_rate, PROFILES["tiktok_us"].commission_rate)

    def test_bad_json_is_noop(self):
        tmp = Path(tempfile.mkdtemp()) / "bad.json"
        tmp.write_text("{not json", encoding="utf-8")
        out = _apply_overrides(self._copy(), tmp)
        self.assertEqual(out["xianyu"].commission_rate, PROFILES["xianyu"].commission_rate)


if __name__ == "__main__":
    unittest.main()
