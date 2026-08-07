import unittest

from hello_agents_framework import ReflectionAgent


class FakeLLM:
    provider = "fake"

    def __init__(self, responses: list[str]) -> None:
        self.responses = iter(responses)
        self.calls: list[list[dict[str, str]]] = []

    def invoke(self, messages: list[dict[str, str]], **kwargs: object) -> str:
        self.calls.append(messages)
        return next(self.responses)


class ReflectionAgentTest(unittest.TestCase):
    def test_refines_then_stops_on_explicit_acceptance(self) -> None:
        llm = FakeLLM(
            [
                "第一版回答",
                "缺少具体案例，请补充。",
                "包含具体案例的第二版回答",
                "无需改进。",
            ]
        )
        agent = ReflectionAgent("反思助手", llm, max_iterations=3)

        answer = agent.run("解释一个概念。")

        self.assertEqual(answer, "包含具体案例的第二版回答")
        self.assertEqual(len(llm.calls), 4)
        self.assertEqual(
            [record["stage"] for record in agent.current_trajectory],
            ["initial", "reflection", "refinement", "reflection"],
        )
        self.assertEqual(
            [message.content for message in agent.get_history()],
            ["解释一个概念。", "包含具体案例的第二版回答"],
        )

    def test_iteration_limit_returns_latest_revision(self) -> None:
        llm = FakeLLM(["v1", "feedback 1", "v2", "feedback 2", "v3"])
        agent = ReflectionAgent("受限助手", llm, max_iterations=2)

        answer = agent.run("改进回答。")

        self.assertEqual(answer, "v3")
        self.assertEqual(len(llm.calls), 5)
        self.assertEqual(len(agent.current_trajectory), 5)

    def test_custom_prompts_are_used_and_trajectory_resets(self) -> None:
        llm = FakeLLM(["first", "无需改进", "second", "无需改进"])
        agent = ReflectionAgent(
            "定制助手",
            llm,
            custom_prompts={
                "initial": "CUSTOM INITIAL: {task}",
                "reflect": "CUSTOM REVIEW: {task} | {content}",
            },
        )

        self.assertEqual(agent.run("任务一"), "first")
        self.assertEqual(agent.run("任务二"), "second")

        self.assertEqual(len(agent.current_trajectory), 2)
        self.assertIn("CUSTOM INITIAL: 任务一", llm.calls[0][-1]["content"])
        self.assertIn("CUSTOM REVIEW: 任务一 | first", llm.calls[1][-1]["content"])

    def test_validates_input_limits_and_custom_prompts(self) -> None:
        llm = FakeLLM([])

        with self.assertRaises(ValueError):
            ReflectionAgent("助手", llm, max_iterations=0)
        with self.assertRaises(ValueError):
            ReflectionAgent("助手", llm, custom_prompts={"unknown": "value"})
        with self.assertRaises(ValueError):
            ReflectionAgent(
                "助手",
                llm,
                custom_prompts={"initial": "{unsupported}"},
            )
        with self.assertRaises(ValueError):
            ReflectionAgent("助手", llm).run("   ")


if __name__ == "__main__":
    unittest.main()
