import unittest

from hello_agents_practice import PlanAndSolveAgent


class FakeLLM:
    provider = "fake"

    def __init__(self, responses: list[str | Exception]) -> None:
        self.responses = iter(responses)
        self.calls: list[list[dict[str, str]]] = []

    def invoke(self, messages: list[dict[str, str]], **kwargs: object) -> str:
        self.calls.append(messages)
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


class PlanAndSolveAgentTest(unittest.TestCase):
    def test_plans_executes_in_order_and_synthesizes(self) -> None:
        llm = FakeLLM(
            [
                '```python\n["计算周二销量", "计算三天总量"]\n```',
                "周二卖出30个",
                "三天共卖出70个",
                "最终答案：70个苹果。",
            ]
        )
        agent = PlanAndSolveAgent("规划助手", llm, max_steps=4)

        answer = agent.run("计算三天苹果销量。")

        self.assertEqual(answer, "最终答案：70个苹果。")
        self.assertEqual(len(llm.calls), 4)
        self.assertIn("周二卖出30个", llm.calls[2][-1]["content"])
        self.assertEqual(
            [step.status for step in agent.current_plan],
            ["completed", "completed"],
        )
        self.assertEqual(
            [step.output for step in agent.current_plan],
            ["周二卖出30个", "三天共卖出70个"],
        )
        self.assertEqual(
            [message.content for message in agent.get_history()],
            ["计算三天苹果销量。", "最终答案：70个苹果。"],
        )

    def test_custom_prompts_accept_raw_python_list(self) -> None:
        llm = FakeLLM(['["计算答案"]', "70", "答案是70。"])
        agent = PlanAndSolveAgent(
            "数学助手",
            llm,
            custom_prompts={
                "planner": "MATH PLAN: {question}",
                "executor": "MATH STEP: {current_step} | {history}",
            },
        )

        self.assertEqual(agent.run("数学题"), "答案是70。")

        self.assertIn("MATH PLAN: 数学题", llm.calls[0][-1]["content"])
        self.assertIn("MATH STEP: 计算答案", llm.calls[1][-1]["content"])

    def test_invalid_plan_returns_terminal_failure(self) -> None:
        llm = FakeLLM(["not a list"])
        agent = PlanAndSolveAgent("规划助手", llm)

        answer = agent.run("复杂问题")

        self.assertEqual(answer, "抱歉，无法生成有效的行动计划。")
        self.assertEqual(agent.current_plan, [])
        self.assertEqual(len(agent.get_history()), 2)

    def test_executor_failure_stops_remaining_steps(self) -> None:
        llm = FakeLLM(
            [
                '["步骤一", "步骤二"]',
                RuntimeError("provider unavailable"),
            ]
        )
        agent = PlanAndSolveAgent("规划助手", llm)

        answer = agent.run("复杂问题")

        self.assertEqual(answer, "抱歉，计划执行失败，未生成最终答案。")
        self.assertEqual(
            [step.status for step in agent.current_plan],
            ["failed", "pending"],
        )
        self.assertEqual(agent.current_plan[0].error, "RuntimeError")
        self.assertEqual(len(llm.calls), 2)

    def test_validates_input_limits_and_custom_prompts(self) -> None:
        llm = FakeLLM([])

        with self.assertRaises(ValueError):
            PlanAndSolveAgent("助手", llm, max_steps=0)
        with self.assertRaises(ValueError):
            PlanAndSolveAgent("助手", llm, custom_prompts={"unknown": "x"})
        with self.assertRaises(ValueError):
            PlanAndSolveAgent(
                "助手",
                llm,
                custom_prompts={"planner": "{unsupported}"},
            )
        with self.assertRaises(ValueError):
            PlanAndSolveAgent("助手", llm).run("   ")


if __name__ == "__main__":
    unittest.main()
