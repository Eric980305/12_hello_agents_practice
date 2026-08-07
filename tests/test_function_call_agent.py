import unittest
from types import SimpleNamespace

from hello_agents_framework import CalculatorTool, FunctionCallAgent, Tool, ToolRegistry


def make_tool_call(
    name: str,
    arguments: str,
    call_id: str = "call_1",
):
    return SimpleNamespace(
        id=call_id,
        type="function",
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def make_completion(content=None, tool_calls=None):
    message = SimpleNamespace(content=content, tool_calls=tool_calls or [])
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeCompletions:
    def __init__(self, responses) -> None:
        self.responses = iter(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return next(self.responses)


class FakeLLM:
    provider = "fake"
    model = "fake-model"

    def __init__(self, responses, with_client: bool = True) -> None:
        self.completions = FakeCompletions(responses)
        if with_client:
            self.client = SimpleNamespace(
                chat=SimpleNamespace(completions=self.completions)
            )


class TypedTool(Tool):
    name = "typed_tool"
    description = "Receive converted integer and boolean values."

    @property
    def parameters(self):
        return {
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
                "enabled": {"type": "boolean"},
            },
            "required": ["count", "enabled"],
            "additionalProperties": False,
        }

    def run(self, parameters):
        return f"{type(parameters['count']).__name__}:{parameters['count']}|{parameters['enabled']}"


def calculator_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register_tool(CalculatorTool())
    return registry


class FunctionCallAgentTest(unittest.TestCase):
    def test_native_tool_call_round_trip(self) -> None:
        llm = FakeLLM(
            [
                make_completion(
                    tool_calls=[
                        make_tool_call(
                            "calculator",
                            '{"expression":"15 * 8 + 32"}',
                        )
                    ]
                ),
                make_completion(content="计算结果是152。"),
            ]
        )
        agent = FunctionCallAgent("函数调用助手", llm, calculator_registry())

        answer = agent.run("请计算 15 * 8 + 32。")

        self.assertEqual(answer, "计算结果是152。")
        self.assertEqual(len(llm.completions.calls), 2)
        schema = llm.completions.calls[0]["tools"][0]["function"]
        self.assertEqual(schema["name"], "calculator")
        self.assertIn("expression", schema["parameters"]["properties"])
        second_messages = llm.completions.calls[1]["messages"]
        self.assertEqual(second_messages[-1]["role"], "tool")
        self.assertEqual(second_messages[-1]["tool_call_id"], "call_1")
        self.assertEqual(second_messages[-1]["content"], "152")
        self.assertEqual(agent.current_tool_calls[0]["status"], "completed")
        self.assertEqual(len(agent.get_history()), 2)

    def test_converts_string_arguments_to_schema_types(self) -> None:
        registry = ToolRegistry()
        registry.register_tool(TypedTool())
        llm = FakeLLM(
            [
                make_completion(
                    tool_calls=[
                        make_tool_call(
                            "typed_tool",
                            '{"count":"3","enabled":"true"}',
                        )
                    ]
                ),
                make_completion(content="done"),
            ]
        )
        agent = FunctionCallAgent("类型助手", llm, registry)

        self.assertEqual(agent.run("调用类型工具"), "done")

        self.assertEqual(
            llm.completions.calls[1]["messages"][-1]["content"],
            "int:3|True",
        )

    def test_registered_function_uses_the_native_tool_path(self) -> None:
        def multiply(left: int, right: int) -> int:
            return left * right

        registry = ToolRegistry()
        registry.register_function(
            name="multiply",
            description="Multiply two integers.",
            func=multiply,
        )
        llm = FakeLLM(
            [
                make_completion(
                    tool_calls=[
                        make_tool_call(
                            "multiply",
                            '{"left":"3","right":"4"}',
                        )
                    ]
                ),
                make_completion(content="12"),
            ]
        )
        agent = FunctionCallAgent("函数工具助手", llm, registry)

        self.assertEqual(agent.run("计算3乘4"), "12")
        self.assertEqual(
            llm.completions.calls[1]["messages"][-1]["content"],
            "12",
        )

    def test_malformed_arguments_become_tool_error_observation(self) -> None:
        llm = FakeLLM(
            [
                make_completion(
                    tool_calls=[make_tool_call("calculator", "not-json")]
                ),
                make_completion(content="无法完成计算。"),
            ]
        )
        agent = FunctionCallAgent("恢复助手", llm, calculator_registry())

        self.assertEqual(agent.run("计算"), "无法完成计算。")

        self.assertEqual(agent.current_tool_calls[0]["status"], "failed")
        self.assertIn(
            "工具调用失败：ValueError",
            llm.completions.calls[1]["messages"][-1]["content"],
        )

    def test_iteration_limit_and_missing_client(self) -> None:
        repeated_call = make_completion(
            tool_calls=[make_tool_call("calculator", '{"expression":"1+1"}')]
        )
        llm = FakeLLM([repeated_call])
        agent = FunctionCallAgent(
            "受限助手",
            llm,
            calculator_registry(),
            max_iterations=1,
        )

        self.assertEqual(
            agent.run("持续调用"),
            "抱歉，函数调用达到迭代上限，未获得最终答案。",
        )

        missing_client = FunctionCallAgent(
            "错误助手",
            FakeLLM([], with_client=False),
            calculator_registry(),
        )
        with self.assertRaises(RuntimeError):
            missing_client.run("测试")


if __name__ == "__main__":
    unittest.main()
