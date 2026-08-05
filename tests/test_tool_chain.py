import unittest

from hello_agents_practice import CalculatorTool, Tool, ToolChain, ToolChainManager, ToolRegistry


class CaptureTool(Tool):
    name = "capture"
    description = "Capture one value for a test."

    def __init__(self) -> None:
        self.value = None

    def run(self, parameters):
        self.value = parameters["value"]
        return "captured"


class ToolChainTest(unittest.TestCase):
    def test_executes_structured_steps_in_order(self) -> None:
        registry = ToolRegistry()
        registry.register_tool(CalculatorTool())
        chain = ToolChain("double_calculation", "Calculate and double the result.")
        chain.add_step(
            "calculator",
            {"expression": "{input}"},
            output_key="first_result",
        )
        chain.add_step(
            "calculator",
            {"expression": "{first_result} * 2"},
            output_key="final_result",
        )

        self.assertEqual(chain.execute(registry, "2 + 3"), "10")

    def test_exact_reference_preserves_non_string_values(self) -> None:
        registry = ToolRegistry()
        capture = CaptureTool()
        registry.register_tool(capture)
        chain = ToolChain("capture_chain", "Preserve structured values.")
        chain.add_step("capture", {"value": "{input}"})

        chain.execute(registry, [[1, 2], [3, 4]])

        self.assertEqual(capture.value, [[1, 2], [3, 4]])

    def test_validates_steps_references_and_manager_names(self) -> None:
        registry = ToolRegistry()
        registry.register_tool(CalculatorTool())
        empty_chain = ToolChain("empty", "No steps.")
        with self.assertRaises(ValueError):
            empty_chain.execute(registry, "2 + 2")

        chain = ToolChain("broken", "Missing context reference.")
        chain.add_step("calculator", {"expression": "{missing}"})
        with self.assertRaises(ValueError):
            chain.execute(registry, "2 + 2")

        with self.assertRaises(ValueError):
            chain.add_step(
                "calculator",
                {"expression": "2 + 2"},
                output_key="step_1_result",
            )

        manager = ToolChainManager(registry)
        manager.register_chain(chain)
        self.assertEqual(manager.list_chains(), ["broken"])
        with self.assertRaises(ValueError):
            manager.register_chain(chain)
        with self.assertRaises(KeyError):
            manager.execute_chain("missing", "2 + 2")


if __name__ == "__main__":
    unittest.main()
