import unittest
from unittest.mock import patch

from src.llm.factory import build_llm


class LlmFactoryTest(unittest.TestCase):
    def test_selects_configured_deepseek_provider_and_model(self):
        with patch("src.llm.factory.config.LLM_PROVIDER", "deepseek"), \
             patch("src.llm.factory.config.DEEPSEEK_API_KEY", "test-key"), \
             patch("src.llm.factory.config.DEEPSEEK_MODEL", "test-model"):
            client = build_llm()
            self.assertEqual(client.name, "deepseek")
            self.assertEqual(client.model, "test-model")


if __name__ == "__main__":
    unittest.main()
