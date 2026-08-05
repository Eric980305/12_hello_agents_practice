import unittest
from datetime import datetime, timezone

from pydantic import ValidationError

from hello_agents_practice.core.message import Message


class MessageTest(unittest.TestCase):
    def test_defaults_are_created_per_message(self) -> None:
        first = Message(content="你好", role="user")
        second = Message(content="你好", role="assistant")

        first.metadata["source"] = "test"

        self.assertEqual(second.metadata, {})
        self.assertIsNotNone(first.timestamp.tzinfo)

    def test_preserves_explicit_metadata_and_timestamp(self) -> None:
        timestamp = datetime(2026, 7, 30, 1, 0, tzinfo=timezone.utc)
        message = Message(
            content="调用完成",
            role="tool",
            timestamp=timestamp,
            metadata={"tool_name": "Search"},
        )

        self.assertEqual(message.timestamp, timestamp)
        self.assertEqual(message.metadata, {"tool_name": "Search"})

    def test_converts_to_api_dict_and_string(self) -> None:
        message = Message(content="系统规则", role="system")

        self.assertEqual(
            message.to_dict(),
            {"role": "system", "content": "系统规则"},
        )
        self.assertEqual(str(message), "[system] 系统规则")

    def test_rejects_unknown_role(self) -> None:
        with self.assertRaises(ValidationError):
            Message(content="错误角色", role="developer")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
