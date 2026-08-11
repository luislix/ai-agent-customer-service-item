import json
import tempfile
import unittest
from pathlib import Path

from src.llm.placeholder import PlaceholderClient
from src.modules.customer.agent import CustomerServiceAgent
from src.modules.customer.knowledge import ProductKnowledgeBase
from src.modules.customer.types import BuyerMessage


class TestProductKnowledgeBase(unittest.TestCase):
    def test_retrieves_only_matching_item_and_formats_facts(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "knowledge.json"
            path.write_text(json.dumps({"products": [
                {"item_id": "A1", "title": "手机支架", "specs": {"夹持桌厚": "1-6cm"},
                 "faq": [{"question": "能夹多厚", "answer": "支持 1-6cm"}]},
                {"item_id": "B2", "title": "另一个支架", "specs": {"夹持桌厚": "2-4cm"}}
            ]}, ensure_ascii=False), encoding="utf-8")
            kb = ProductKnowledgeBase.from_json(path)
            result = kb.context("能夹多厚", item_id="A1")
            self.assertIn("1-6cm", result)
            self.assertNotIn("2-4cm", result)
            self.assertIn("标准答案", result)

    def test_agent_injects_retrieved_context_before_llm(self):
        kb = ProductKnowledgeBase.from_json(Path("data/product_knowledge.example.json"))
        agent = CustomerServiceAgent(PlaceholderClient(), kb)
        reply = agent.handle(BuyerMessage("c", "b", "能夹多厚的桌子？", item_id="A1", item_title="手机支架"))
        self.assertTrue(reply.text)


if __name__ == "__main__":
    unittest.main()
