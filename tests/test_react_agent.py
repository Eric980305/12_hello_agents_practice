import unittest

from hello_agents_practice import (
    CalculatorTool,
    ReActAgent,
    ToolRegistry,
)


class FakeLLM:
    provider = "fake"

    def __init__(self, responses: list[str]) -> None:
        self.responses = iter(responses)
        self.calls: list[list[dict[str, str]]] = []

    def invoke(self, messages: list[dict[str, str]], **kwargs: object) -> str:
        self.calls.append(messages)
        return next(self.responses)


def create_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register_tool(CalculatorTool())
    return registry


class ReActAgentTest(unittest.TestCase):
    def test_executes_one_tool_then_finishes(self) -> None:
        llm = FakeLLM(
            [
                "Thought: 需要精确计算。\nAction: calculator[15 * 8 + 32]",
                "Thought: 已获得计算结果。\nAction: Finish[计算结果是 152。]",
            ]
        )
        agent = ReActAgent("计算助手", llm, create_registry())

        answer = agent.run("请计算 15 * 8 + 32。")

        self.assertEqual(answer, "计算结果是 152。")
        self.assertEqual(len(llm.calls), 2)
        self.assertIn("calculator", llm.calls[0][-1]["content"])
        self.assertIn("Observation: 152", llm.calls[1][-1]["content"])
        self.assertEqual(
            agent.current_history,
            ["Action: calculator[15 * 8 + 32]", "Observation: 152"],
        )
        self.assertEqual(
            [message.content for message in agent.get_history()],
            ["请计算 15 * 8 + 32。", "计算结果是 152。"],
        )

    def test_uses_only_first_pair_when_model_emits_multiple_pairs(self) -> None:
        llm = FakeLLM(
            [
                (
                    "Thought: 需要精确计算。\n"
                    "Action: calculator[15 * 8 + 32]"
                    "Thought: 计算结果为 152。\n"
                    "Action: Finish[152]"
                ),
                "Thought: 工具已经确认结果。\nAction: Finish[152]",
            ]
        )
        agent = ReActAgent("计算助手", llm, create_registry())

        answer = agent.run("请计算 15 * 8 + 32。")

        self.assertEqual(answer, "152")
        self.assertEqual(
            agent.current_history,
            ["Action: calculator[15 * 8 + 32]", "Observation: 152"],
        )

    def test_malformed_and_unknown_actions_become_observations(self) -> None:
        llm = FakeLLM(
            [
                "这不是约定格式",
                "Thought: 尝试不存在的工具。\nAction: missing[value]",
                "Thought: 应停止并说明。\nAction: Finish[无法使用该工具。]",
            ]
        )
        agent = ReActAgent("恢复助手", llm, create_registry(), max_steps=3)

        answer = agent.run("调用一个不存在的工具。")

        self.assertEqual(answer, "无法使用该工具。")
        self.assertIn("Observation: 模型输出格式无效。", agent.current_history)
        self.assertIn("Observation: 工具调用失败：KeyError", agent.current_history)

    def test_step_limit_returns_explicit_terminal_answer(self) -> None:
        llm = FakeLLM(
            [
                "Thought: 第一次计算。\nAction: calculator[1 + 1]",
                "Thought: 再次计算。\nAction: calculator[2 + 2]",
            ]
        )
        agent = ReActAgent("受限助手", llm, create_registry(), max_steps=2)

        answer = agent.run("持续计算。")

        self.assertEqual(answer, "抱歉，我无法在限定步数内完成这个任务。")
        self.assertEqual(len(llm.calls), 2)
        self.assertEqual(len(agent.get_history()), 2)

    def test_validates_limits_registry_and_prompt_contract(self) -> None:
        llm = FakeLLM([])

        with self.assertRaises(ValueError):
            ReActAgent("助手", llm, create_registry(), max_steps=0)
        with self.assertRaises(TypeError):
            ReActAgent("助手", llm, object())
        with self.assertRaises(ValueError):
            ReActAgent(
                "助手",
                llm,
                create_registry(),
                custom_prompt="Question: {question}",
            )


if __name__ == "__main__":
    unittest.main()
