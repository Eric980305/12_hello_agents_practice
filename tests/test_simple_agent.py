import unittest
from typing import Any, cast

from hello_agents_framework import CalculatorTool, Config, HelloAgentsLLM, SimpleAgent


class FakeLLM:
    provider = "auto"

    def __init__(
        self,
        responses: list[str] | None = None,
        stream_chunks: list[str] | None = None,
    ) -> None:
        self.responses = list(responses or [])
        self.stream_chunks = list(stream_chunks or [])
        self.calls: list[list[dict[str, str]]] = []

    def invoke(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        self.calls.append(messages)
        return self.responses.pop(0)

    def stream_invoke(self, messages: list[dict[str, str]], **kwargs: Any):
        self.calls.append(messages)
        yield from self.stream_chunks


def fake_llm(
    responses: list[str] | None = None,
    stream_chunks: list[str] | None = None,
) -> tuple[HelloAgentsLLM, FakeLLM]:
    backend = FakeLLM(responses, stream_chunks)
    return cast(HelloAgentsLLM, backend), backend


class SimpleAgentTest(unittest.TestCase):
    def test_direct_chat_uses_history_and_records_final_turn(self) -> None:
        llm, backend = fake_llm(["第一次回答", "第二次回答"])
        agent = SimpleAgent(name="assistant", llm=llm, system_prompt="系统规则")

        self.assertEqual(agent.run("问题一"), "第一次回答")
        self.assertEqual(agent.run("问题二"), "第二次回答")

        second_messages = backend.calls[1]
        self.assertEqual(second_messages[0], {"role": "system", "content": "系统规则"})
        self.assertIn({"role": "user", "content": "问题一"}, second_messages)
        self.assertIn({"role": "assistant", "content": "第一次回答"}, second_messages)
        self.assertEqual(len(agent.get_history()), 4)

    def test_registered_calculator_runs_in_a_bounded_loop(self) -> None:
        llm, backend = fake_llm(
            ["[TOOL_CALL:calculator:15 * 8 + 32]", "计算结果是152。"]
        )
        agent = SimpleAgent(name="calculator", llm=llm)
        agent.add_tool(CalculatorTool())

        response = agent.run("请计算", max_tool_iterations=2)

        self.assertEqual(response, "计算结果是152。")
        self.assertIn("152", backend.calls[1][-1]["content"])
        self.assertEqual(agent.list_tools(), ["calculator"])
        self.assertTrue(agent.has_tools())
        self.assertEqual(len(agent.get_history()), 2)

    def test_tool_limit_stops_execution_and_strips_new_calls(self) -> None:
        llm, backend = fake_llm(
            [
                "[TOOL_CALL:calculator:1 + 1]",
                "[TOOL_CALL:calculator:2 + 2]",
            ]
        )
        agent = SimpleAgent(name="bounded", llm=llm)
        agent.add_tool(CalculatorTool())

        response = agent.run("持续调用", max_tool_iterations=1)

        self.assertEqual(response, "工具调用达到上限。")
        self.assertEqual(len(backend.calls), 2)

    def test_streaming_records_complete_response_without_tools(self) -> None:
        llm, _ = fake_llm(stream_chunks=["你", "好"])
        agent = SimpleAgent(name="stream", llm=llm)

        chunks = list(agent.stream_run("问候"))

        self.assertEqual(chunks, ["你", "好"])
        self.assertEqual(agent.get_history()[-1].content, "你好")

    def test_tool_management_and_validation(self) -> None:
        llm, _ = fake_llm(["unused"])
        agent = SimpleAgent(
            name="tools",
            llm=llm,
            config=Config(max_history_length=4),
        )

        self.assertFalse(agent.has_tools())
        agent.add_tool(CalculatorTool())
        with self.assertRaises(RuntimeError):
            list(agent.stream_run("不能流式调用工具"))
        self.assertTrue(agent.remove_tool("calculator"))
        self.assertFalse(agent.has_tools())
        with self.assertRaises(ValueError):
            agent.run("   ")
        with self.assertRaises(ValueError):
            agent.run("hello", max_tool_iterations=0)
        with self.assertRaises(ValueError):
            agent.run("hello", max_tool_iterations=11)


if __name__ == "__main__":
    unittest.main()
