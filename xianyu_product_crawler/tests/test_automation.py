from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from xianyu_product_crawler.automation import AutomationTaskStore
from xianyu_product_crawler.receiver import CaptureStore, make_handler


def _capture(item_id: str = "1234567890") -> dict:
    return {
        "source_url": f"https://www.goofish.com/item?id={item_id}",
        "item_id_hint": item_id,
        "visible": {"title": "自动化测试商品"},
    }


class AutomationTests(unittest.TestCase):
    def test_task_lifecycle_and_single_active_task(self):
        tasks = AutomationTaskStore()
        with tempfile.TemporaryDirectory() as directory:
            task = tasks.create("手机支架", search_url="https://www.goofish.com/search?q=x", output_dir=directory)
            self.assertEqual(task.state, "queued")
            claimed = tasks.claim_next()
            self.assertEqual(claimed.id, task.id)
            with self.assertRaisesRegex(RuntimeError, "运行中"):
                tasks.create("项链", search_url="https://www.goofish.com/search?q=x", output_dir=directory)
            tasks.record_event(task.id, {"state": "running", "discovered": 2, "collected": 1, "message": "已采集 1 条"})
            tasks.record_event(task.id, {"state": "completed", "discovered": 2, "collected": 2})
            finished = tasks.wait(task.id, timeout=0.1)
            self.assertEqual(finished.state, "completed")
            self.assertEqual(finished.collected, 2)
            with self.assertRaisesRegex(ValueError, "不能回退"):
                tasks.record_event(task.id, {"state": "running"})

    def test_invalid_event_cannot_change_counters(self):
        tasks = AutomationTaskStore()
        task = tasks.create("手机支架", search_url="https://www.goofish.com/search?q=x", output_dir="out")
        tasks.claim_next()
        with self.assertRaisesRegex(ValueError, "非负整数"):
            tasks.record_event(task.id, {"collected": -1})

    def test_http_control_and_task_scoped_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tasks = AutomationTaskStore()
            task = tasks.create("手机支架", search_url="https://www.goofish.com/search?q=x", output_dir=root / "runs")
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(CaptureStore(root / "captures", "token"), tasks))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                with self.assertRaises(HTTPError) as failed:
                    urlopen(Request(base + "/automation/next", headers={"X-Collector-Token": "bad"}), timeout=2)
                self.assertEqual(failed.exception.code, 401)
                with urlopen(Request(base + "/automation/next", headers={"X-Collector-Token": "token"}), timeout=2) as response:
                    claimed = json.loads(response.read())
                self.assertEqual(claimed["id"], task.id)
                payload = json.dumps(_capture()).encode()
                request = Request(
                    f"{base}/captures/{task.id}",
                    data=payload,
                    method="POST",
                    headers={"Content-Type": "application/json", "X-Collector-Token": "token"},
                )
                with urlopen(request, timeout=2) as response:
                    self.assertEqual(response.status, 201)
                self.assertTrue((root / "runs" / task.id / "inbox" / "item_1234567890.json").exists())
                event = json.dumps({"state": "completed", "collected": 1}).encode()
                request = Request(
                    f"{base}/automation/tasks/{task.id}/events",
                    data=event,
                    method="POST",
                    headers={"Content-Type": "application/json", "X-Collector-Token": "token"},
                )
                with urlopen(request, timeout=2) as response:
                    self.assertEqual(json.loads(response.read())["state"], "completed")
            finally:
                server.shutdown()
                thread.join(timeout=2)
                server.server_close()


if __name__ == "__main__":
    unittest.main()
