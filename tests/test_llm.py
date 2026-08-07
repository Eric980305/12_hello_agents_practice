import unittest
from unittest.mock import Mock, patch

from hello_agents_framework.core.llm import HelloAgentsLLM


class HelloAgentsLLMTest(unittest.TestCase):
    @patch("hello_agents_framework.core.llm.OpenAI")
    def test_invoke_returns_complete_response(self, openai_mock: Mock) -> None:
        sdk = openai_mock.return_value
        sdk.chat.completions.create.return_value = Mock(
            choices=[Mock(message=Mock(content="hello"))]
        )
        llm = HelloAgentsLLM("test-model", "test-key", "https://example.com/v1")

        result = llm.invoke([{"role": "user", "content": "hi"}], temperature=0.2)

        self.assertEqual(result, "hello")
        self.assertEqual(llm.provider, "auto")
        sdk.chat.completions.create.assert_called_once_with(
            model="test-model",
            messages=[{"role": "user", "content": "hi"}],
            stream=False,
            temperature=0.2,
        )

    @patch("hello_agents_framework.core.llm.OpenAI")
    def test_stream_invoke_yields_nonempty_chunks(self, openai_mock: Mock) -> None:
        sdk = openai_mock.return_value
        sdk.chat.completions.create.return_value = [
            Mock(choices=[Mock(delta=Mock(content="你"))]),
            Mock(choices=[Mock(delta=Mock(content=""))]),
            Mock(choices=[Mock(delta=Mock(content="好"))]),
        ]
        llm = HelloAgentsLLM("test-model", "test-key", "https://example.com/v1")

        chunks = list(llm.stream_invoke([{"role": "user", "content": "hi"}]))

        self.assertEqual(chunks, ["你", "好"])


if __name__ == "__main__":
    unittest.main()
