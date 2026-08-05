import unittest

from hello_agents_practice.tools import CalculatorTool, FunctionTool, Tool, ToolRegistry


class EchoTool(Tool):
    name = "echo"
    description = "Return the input parameter."

    def run(self, parameters):
        return parameters["input"]


class ToolRegistryTest(unittest.TestCase):
    def test_registers_describes_executes_and_removes_tools(self) -> None:
        registry = ToolRegistry()
        registry.register_tool(EchoTool())

        self.assertEqual(registry.list_tools(), ["echo"])
        self.assertIn("echo", registry.get_tools_description())
        self.assertEqual(registry.execute_tool("echo", {"input": "hello"}), "hello")
        self.assertTrue(registry.unregister("echo"))
        self.assertFalse(registry.unregister("echo"))
        self.assertEqual(registry.get_tools_description(), "暂无可用工具")

    def test_rejects_duplicates_and_unknown_dispatch(self) -> None:
        registry = ToolRegistry()
        registry.register_tool(EchoTool())

        with self.assertRaises(ValueError):
            registry.register_tool(EchoTool())
        with self.assertRaises(KeyError):
            registry.execute_tool("missing", {})

    def test_registers_functions_through_the_same_tool_registry(self) -> None:
        def repeat(text: str, count: int = 2) -> str:
            return text * count

        registry = ToolRegistry()
        tool = registry.register_function(
            name="repeat",
            description="Repeat text a fixed number of times.",
            func=repeat,
        )

        self.assertIsInstance(tool, FunctionTool)
        self.assertIs(registry.get_tool("repeat"), tool)
        self.assertEqual(registry.list_tools(), ["repeat"])
        self.assertEqual(
            registry.execute_tool("repeat", {"text": "ha", "count": 3}),
            "hahaha",
        )
        self.assertEqual(registry.execute_tool("repeat", {"text": "ha"}), "haha")
        self.assertEqual(tool.parameters["required"], ["text"])
        self.assertEqual(
            tool.parameters["properties"]["count"]["type"],
            "integer",
        )

        with self.assertRaises(ValueError):
            registry.register_function(
                name="repeat",
                description="Duplicate name.",
                func=repeat,
            )

    def test_function_adapter_rejects_unsupported_signatures(self) -> None:
        def variadic(*values: str) -> str:
            return "".join(values)

        with self.assertRaises(ValueError):
            FunctionTool("variadic", "Unsupported variadic function.", variadic)


class CalculatorToolTest(unittest.TestCase):
    def test_evaluates_bounded_arithmetic(self) -> None:
        calculator = CalculatorTool()

        self.assertEqual(
            calculator.run({"expression": "15 * 8 + 32"}),
            "152",
        )
        self.assertEqual(calculator.run({"input": "-(2 + 3)"}), "-5")

    def test_rejects_code_and_resource_abuse(self) -> None:
        calculator = CalculatorTool()
        invalid = (
            "__import__('os').system('pwd')",
            "2 ** 1000",
            "1 / 0",
            "True + 1",
        )

        for expression in invalid:
            with self.subTest(expression=expression), self.assertRaises(Exception):
                calculator.run({"expression": expression})


if __name__ == "__main__":
    unittest.main()
