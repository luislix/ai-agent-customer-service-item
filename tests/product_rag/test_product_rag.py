import json
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
from datetime import datetime, timezone, timedelta
from pathlib import Path

from src.modules.product_rag.chunker import build_chunks
from src.modules.product_rag.memory import InMemoryKnowledgeStore
from src.modules.product_rag.normalizer import snapshot_hash
from src.modules.product_rag.service import ProductRagService
from src.modules.product_rag.validator import validate_and_normalize
from src.modules.product_rag.errors import ProductSnapshotValidationError
from src.modules.product_rag.embedding import LocalBgeM3EmbeddingProvider


class FakeEmbedding:
    model = "fake"

    def embed(self, texts):
        return [[1.0, 0.0] if "厚" in text or "规格" in text else [0.0, 1.0] for text in texts]


def product(**overrides):
    value = {
        "item_id": "A1", "title": "手机支架", "description": "适用于桌面夹持",
        "specs": {"夹持桌厚": "1-6cm"}, "condition": "全新",
        "inventory": {"status": "in_stock", "quantity": 8},
        "price": {"sale_price": 39, "currency": "CNY"},
        "shipping": {"dispatch_sla_hours": 24, "carrier": "中通", "fee": 0},
        "after_sale": "质量问题可售后", "faq": [{"question": "能夹多厚？", "answer": "支持1-6cm"}],
        "source_url": "https://example.com/A1",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    value.update(overrides)
    return value


class TestProductRag(unittest.TestCase):
    def test_local_bge_provider_batches_and_normalizes_output(self):
        class FakeModel:
            def encode(self, texts, **kwargs):
                self.args = (texts, kwargs)
                return [[0.6, 0.8] for _ in texts]

        provider = LocalBgeM3EmbeddingProvider(device="cpu", batch_size=4)
        self.assertEqual(provider.dimension, 1024)
        fake = FakeModel()
        fake_module = types.SimpleNamespace(SentenceTransformer=lambda *args, **kwargs: fake)
        with patch.dict(sys.modules, {"sentence_transformers": fake_module}):
            self.assertEqual(provider.embed([]), [])
            self.assertEqual(provider.embed(["a", "b"]), [[0.6, 0.8], [0.6, 0.8]])
            self.assertEqual(fake.args[1]["batch_size"], 4)
            self.assertTrue(fake.args[1]["normalize_embeddings"])

    def test_reindex_reembeds_same_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "products.jsonl"
            path.write_text(json.dumps(product(), ensure_ascii=False) + "\n", encoding="utf-8")
            store = InMemoryKnowledgeStore()
            service = ProductRagService(store, FakeEmbedding(), min_score=0.5)
            self.assertEqual(service.import_file(path).accepted, 1)
            self.assertEqual(service.import_file(path).skipped, 1)
            self.assertEqual(service.import_file(path, force_reindex=True).accepted, 1)

    def test_validation_rejects_missing_timezone_and_invalid_inventory(self):
        with self.assertRaises(ProductSnapshotValidationError):
            validate_and_normalize(product(updated_at="2026-08-06T12:00:00"))
        with self.assertRaises(ProductSnapshotValidationError):
            validate_and_normalize(product(inventory={"status": "maybe"}))

    def test_stage_one_contract_is_normalized_and_chunked(self):
        normalized = validate_and_normalize(product(
            category="手机配件",
            specifications={"材质": "铝合金"},
            included_items=["支架", "说明书", "支架"],
            pricing={"sale_price": "49.90", "currency": "CNY"},
        ))
        self.assertEqual(normalized["specifications"], {"材质": "铝合金"})
        self.assertEqual(normalized["specs"], {"材质": "铝合金"})
        self.assertEqual(normalized["pricing"], {"sale_price": "49.90", "currency": "CNY"})
        chunks = build_chunks(normalized, "A1:stage-one", snapshot_hash(normalized))
        basic = next(chunk.content for chunk in chunks if chunk.kind == "basic_info")
        self.assertIn("商品类目：手机配件", basic)
        self.assertIn("商品配件：支架、说明书", basic)

    def test_price_range_and_shipping_note_are_normalized_and_chunked(self):
        normalized = validate_and_normalize(product(
            pricing={"min_price": "4.38", "max_price": "109", "currency": "CNY"},
            shipping={"free_shipping": True, "fee": "0", "note": "偏远地区除外"},
        ))
        self.assertEqual(normalized["pricing"], {"min_price": "4.38", "max_price": "109", "currency": "CNY"})
        self.assertEqual(normalized["shipping"]["note"], "偏远地区除外")
        chunks = build_chunks(normalized, "A1:range", snapshot_hash(normalized))
        commercial = next(chunk.content for chunk in chunks if chunk.kind == "commercial")
        shipping = next(chunk.content for chunk in chunks if chunk.kind == "shipping")
        self.assertIn("售价区间：4.38 - 109 CNY", commercial)
        self.assertIn("物流说明：偏远地区除外", shipping)

    def test_chunk_types_and_dynamic_expiry(self):
        normalized = validate_and_normalize(product())
        chunks = build_chunks(normalized, "A1:abc", snapshot_hash(normalized))
        kinds = {chunk.kind for chunk in chunks}
        self.assertTrue({"basic_info", "specification", "commercial", "shipping", "after_sale", "faq"} <= kinds)
        self.assertTrue(all(c.valid_until is not None for c in chunks if c.kind in {"commercial", "shipping"}))
        self.assertTrue(all(c.valid_until is None for c in chunks if c.kind not in {"commercial", "shipping"}))

    def test_retrieval_isolated_by_item_and_expired_dynamic_is_excluded(self):
        a = validate_and_normalize(product())
        b = validate_and_normalize(product(item_id="B2", title="另一件商品", source_url="https://example.com/B2"))
        chunks = build_chunks(a, "A1:a", snapshot_hash(a)) + build_chunks(b, "B2:b", snapshot_hash(b))
        # make the A1 commercial chunk expired
        expired = []
        for chunk in chunks:
            if chunk.item_id == "A1" and chunk.kind == "commercial":
                chunk = chunk.__class__(**{**chunk.__dict__, "valid_until": datetime.now(timezone.utc) - timedelta(hours=1)})
            if not chunk.embedding:
                chunk = chunk.__class__(**{**chunk.__dict__, "embedding": (1.0, 0.0) if "规格" in chunk.content else (0.0, 1.0)})
            expired.append(chunk)
        store = InMemoryKnowledgeStore(expired)
        service = ProductRagService(store, FakeEmbedding(), min_score=0.5)
        result = service.retrieve("A1", "规格 厚度")
        self.assertTrue(result)
        self.assertTrue(all(row.item_id == "A1" for row in result))
        self.assertFalse(any(row.kind == "commercial" for row in result))

    def test_import_jsonl_reports_bad_line_without_stopping(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "products.jsonl"
            path.write_text(json.dumps(product(), ensure_ascii=False) + "\n{bad json}\n", encoding="utf-8")
            service = ProductRagService(InMemoryKnowledgeStore(), FakeEmbedding(), min_score=0.5)
            report = service.import_file(path)
            self.assertEqual(report.accepted, 1)
            self.assertEqual(report.failed, 1)
            self.assertEqual(report.errors[0].line_number, 2)
            second = service.import_file(path)
            self.assertEqual(second.skipped, 1)


if __name__ == "__main__":
    unittest.main()
