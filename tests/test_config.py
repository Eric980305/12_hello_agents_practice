import os
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from hello_agents_framework.core.config import Config


class ConfigTest(unittest.TestCase):
    def test_defaults_do_not_assume_a_remote_model(self) -> None:
        config = Config()

        self.assertIsNone(config.model_id)
        self.assertEqual(config.provider, "auto")
        self.assertIsNone(config.api_key)
        self.assertIsNone(config.base_url)
        self.assertEqual(config.temperature, 0.7)

    def test_loads_generic_openai_compatible_environment(self) -> None:
        environment = {
            "LLM_MODEL_ID": "gpt-5.6-luna",
            "LLM_PROVIDER": "auto",
            "LLM_API_KEY": "test-secret",
            "LLM_BASE_URL": "https://example.com/v1",
            "LLM_TEMPERATURE": "0.2",
            "LLM_MAX_TOKENS": "4096",
            "LLM_TIMEOUT": "90",
            "DEBUG": "true",
            "LOG_LEVEL": "warning",
            "MAX_HISTORY_LENGTH": "50",
        }

        with patch.dict(os.environ, environment, clear=True):
            config = Config.from_env()

        self.assertEqual(config.model_id, "gpt-5.6-luna")
        self.assertEqual(config.provider, "auto")
        self.assertEqual(config.api_key.get_secret_value(), "test-secret")
        self.assertEqual(config.base_url, "https://example.com/v1")
        self.assertEqual(config.temperature, 0.2)
        self.assertEqual(config.max_tokens, 4096)
        self.assertEqual(config.timeout, 90)
        self.assertTrue(config.debug)
        self.assertEqual(config.log_level, "WARNING")
        self.assertEqual(config.max_history_length, 50)

    def test_export_excludes_api_key(self) -> None:
        config = Config(api_key="test-secret", model_id="test-model")

        exported = config.to_dict()

        self.assertNotIn("api_key", exported)
        self.assertNotIn("test-secret", repr(config))

    def test_rejects_invalid_limits_and_unknown_fields(self) -> None:
        invalid_values = (
            {"temperature": 2.1},
            {"max_tokens": 0},
            {"timeout": 0},
            {"max_history_length": 0},
            {"unknown": "value"},
        )

        for values in invalid_values:
            with self.subTest(values=values), self.assertRaises(ValidationError):
                Config(**values)


if __name__ == "__main__":
    unittest.main()
