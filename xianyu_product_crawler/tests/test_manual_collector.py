from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from xianyu_product_crawler.build_dataset import build_captures
from xianyu_product_crawler.receiver import CaptureStore, load_or_create_token, make_handler


def capture(item_id: str = "1234567890") -> dict:
    return {
        "source_url": f"https://www.goofish.com/item?id={item_id}",
        "item_id_hint": item_id,
        "collected_at": "2026-08-10T10:00:00+00:00",
        "visible": {
            "title": "测试手机",
            "description": "联系电话 13812345678",
            "specs": {"容量": "128GB"},
            "price": {"sale_price": "2999", "currency": "CNY"},
        },
    }


class ManualCollectorTests(unittest.TestCase):
    def test_store_only_accepts_goofish_and_redacts_content(self):
        with tempfile.TemporaryDirectory() as directory:
            store = CaptureStore(directory, "test-token")
            path = store.save(capture())
            saved = path.read_text(encoding="utf-8")
            self.assertIn("[REDACTED_PHONE]", saved)
            self.assertNotIn("13812345678", saved)
            with self.assertRaisesRegex(ValueError, "goofish"):
                store.save({**capture(), "source_url": "https://example.com/item?id=1234567890"})

    def test_repeated_capture_replaces_same_item(self):
        with tempfile.TemporaryDirectory() as directory:
            store = CaptureStore(directory, "test-token")
            first = store.save(capture())
            updated = capture()
            updated["visible"]["description"] = "更新后的页面资料"
            second = store.save(updated)
            files = list((Path(directory) / "inbox").glob("*.json"))
            self.assertEqual(first, second)
            self.assertEqual(files, [first])
            self.assertIn("更新后的页面资料", second.read_text(encoding="utf-8"))

    def test_token_is_stable_for_same_output_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            first = load_or_create_token(directory)
            self.assertEqual(first, load_or_create_token(directory))
            self.assertTrue((Path(directory) / ".collector-token").exists())

    def test_capture_builds_contract_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            inbox = Path(directory) / "inbox"
            inbox.mkdir()
            (inbox / "capture.json").write_text(json.dumps(capture(), ensure_ascii=False), encoding="utf-8")
            records, failures, _ = build_captures(inbox)
            self.assertEqual(failures, [])
            self.assertEqual(records[0]["item_id"], "1234567890")
            self.assertEqual(records[0]["price"]["sale_price"], "2999")

    def test_capture_preserves_stage_one_category_and_included_items(self):
        with tempfile.TemporaryDirectory() as directory:
            inbox = Path(directory) / "inbox"
            inbox.mkdir()
            row = capture()
            row["visible"].update({
                "category": "手机配件",
                "specifications": {"容量": "128GB"},
                "included_items": ["手机", "数据线", "手机"],
                "pricing": {"sale_price": "2999", "currency": "CNY"},
            })
            (inbox / "capture.json").write_text(json.dumps(row, ensure_ascii=False), encoding="utf-8")
            records, failures, _ = build_captures(inbox)
            self.assertEqual(failures, [])
            self.assertEqual(records[0]["category"], "手机配件")
            self.assertEqual(records[0]["included_items"], ["手机", "数据线"])
            self.assertEqual(records[0]["pricing"], records[0]["price"])

    def test_capture_preserves_price_range_and_shipping_note(self):
        with tempfile.TemporaryDirectory() as directory:
            inbox = Path(directory) / "inbox"
            inbox.mkdir()
            row = capture()
            row["visible"].update({
                "pricing": {"min_price": "4.38", "max_price": "109", "currency": "CNY"},
                "shipping": {"free_shipping": True, "fee": "0", "note": "偏远地区除外"},
            })
            (inbox / "capture.json").write_text(json.dumps(row, ensure_ascii=False), encoding="utf-8")
            records, failures, _ = build_captures(inbox)
            self.assertEqual(failures, [])
            self.assertEqual(records[0]["pricing"], {"min_price": "4.38", "max_price": "109", "currency": "CNY"})
            self.assertEqual(records[0]["shipping"]["note"], "偏远地区除外")

    def test_capture_without_item_id_becomes_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            inbox = Path(directory) / "inbox"
            inbox.mkdir()
            bad = capture("")
            bad["source_url"] = "https://www.goofish.com/item"
            bad["item_id_hint"] = ""
            (inbox / "bad.json").write_text(json.dumps(bad), encoding="utf-8")
            records, failures, _ = build_captures(inbox)
            self.assertEqual(records, [])
            self.assertEqual(len(failures), 1)

    def test_generic_homepage_title_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            inbox = Path(directory) / "inbox"
            inbox.mkdir()
            bad = capture()
            bad["visible"]["title"] = "为你推荐"
            (inbox / "generic.json").write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
            records, failures, _ = build_captures(inbox)
            self.assertEqual(records, [])
            self.assertIn("通用内容", failures[0].error)

    def test_receiver_rejects_bad_token_and_accepts_local_capture(self):
        from http.server import ThreadingHTTPServer

        with tempfile.TemporaryDirectory() as directory:
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(CaptureStore(directory, "correct-token")))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            url = f"http://127.0.0.1:{server.server_port}/captures"
            data = json.dumps(capture()).encode("utf-8")
            try:
                request = Request(url, data=data, method="POST", headers={"Content-Type": "application/json", "X-Collector-Token": "wrong"})
                with self.assertRaises(HTTPError) as failed:
                    urlopen(request, timeout=2)
                self.assertEqual(failed.exception.code, 401)
                self.assertFalse((Path(directory) / "inbox").exists())
                request = Request(url, data=data, method="POST", headers={"Content-Type": "application/json", "X-Collector-Token": "correct-token"})
                with urlopen(request, timeout=2) as response:
                    self.assertEqual(response.status, 201)
                self.assertEqual(len(list((Path(directory) / "inbox").glob("*.json"))), 1)
            finally:
                server.shutdown()
                thread.join(timeout=2)
                server.server_close()


if __name__ == "__main__":
    unittest.main()
