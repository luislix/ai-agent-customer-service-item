import tempfile
import unittest
from pathlib import Path

from src.modules.product_rag.manual_ingestion import (
    KnowledgeDraftInput,
    ManualKnowledgeIngestion,
    ManualKnowledgeIngestionStore,
)
from src.modules.product_rag.contracts import ImportReport


class RecordingImporter:
    def __init__(self):
        self.records = []

    def import_records(self, records):
        self.records.extend(records)


class FailingImporter:
    def import_records(self, records):
        return ImportReport(failed=1)


class TestManualKnowledgeIngestion(unittest.TestCase):
    def setUp(self):
        self.db = str(Path(tempfile.mkdtemp()) / "knowledge.db")
        self.store = ManualKnowledgeIngestionStore(self.db)
        self.importer = RecordingImporter()
        self.service = ManualKnowledgeIngestion(self.store, self.importer)

    def test_draft_is_not_published_when_created(self):
        draft = self.service.create_draft(KnowledgeDraftInput(
            source_pick_id=7,
            source_item_id="supplier-7",
            title="手机支架",
            source_url="https://supplier.example/items/7",
            suggested_price=39,
            currency="CNY",
        ))

        self.assertEqual(draft.status, "draft")
        self.assertEqual(self.importer.records, [])
        self.assertEqual(self.store.get(draft.id).status, "draft")

    def test_publish_requires_xianyu_item_id_and_valid_snapshot(self):
        draft = self.service.create_draft(KnowledgeDraftInput(
            source_pick_id=7, source_item_id="supplier-7", title="手机支架",
            source_url="https://supplier.example/items/7", suggested_price=39, currency="CNY",
        ))

        with self.assertRaises(ValueError):
            self.service.publish(draft.id, "", {"specs": {"夹持桌厚": "1-6cm"}})
        with self.assertRaises(ValueError):
            self.service.publish(draft.id, "XY-7", {"inventory": {"status": "invalid"}})
        self.assertEqual(self.importer.records, [])

    def test_publish_uses_xianyu_id_and_marks_draft_published(self):
        draft = self.service.create_draft(KnowledgeDraftInput(
            source_pick_id=7, source_item_id="supplier-7", title="手机支架",
            source_url="https://supplier.example/items/7", suggested_price=39, currency="CNY",
        ))

        result = self.service.publish(draft.id, "XY-7", {
            "specs": {"夹持桌厚": "1-6cm"},
            "inventory": {"status": "in_stock", "quantity": 8},
            "shipping": {"dispatch_sla_hours": 24, "free_shipping": True},
            "after_sale": "质量问题可售后",
            "faq": [{"question": "能夹多厚？", "answer": "支持 1-6cm"}],
        })

        self.assertEqual(result["item_id"], "XY-7")
        self.assertEqual(result["price"], {"sale_price": "39.0", "currency": "CNY"})
        self.assertEqual(self.importer.records, [result])
        self.assertEqual(self.store.get(draft.id).status, "published")

    def test_same_approved_pick_cannot_create_two_drafts(self):
        source = KnowledgeDraftInput(7, "supplier-7", "手机支架", "https://supplier.example/items/7", 39, "CNY")
        self.service.create_draft(source)
        with self.assertRaises(ValueError):
            self.service.create_draft(source)

    def test_failed_rag_import_keeps_draft_unpublished(self):
        draft = ManualKnowledgeIngestion(self.store, FailingImporter()).create_draft(KnowledgeDraftInput(
            source_pick_id=7, source_item_id="supplier-7", title="手机支架",
            source_url="https://supplier.example/items/7", suggested_price=39, currency="CNY",
        ))

        with self.assertRaises(RuntimeError):
            ManualKnowledgeIngestion(self.store, FailingImporter()).publish(draft.id, "XY-7", {})
        self.assertEqual(self.store.get(draft.id).status, "draft")


if __name__ == "__main__":
    unittest.main()
