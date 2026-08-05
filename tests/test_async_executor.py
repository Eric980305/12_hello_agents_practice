import asyncio
import threading
import time
import unittest

from hello_agents_practice import AsyncToolExecutor, CalculatorTool, Tool, ToolRegistry


class CountingTool(Tool):
    name = "counting"
    description = "Track concurrent executions for a test."

    def __init__(self, delay: float = 0.02) -> None:
        self.delay = delay
        self.active = 0
        self.maximum_active = 0
        self._lock = threading.Lock()

    def run(self, parameters):
        with self._lock:
            self.active += 1
            self.maximum_active = max(self.maximum_active, self.active)
        try:
            time.sleep(self.delay)
            return str(parameters["value"])
        finally:
            with self._lock:
                self.active -= 1


class AsyncToolExecutorTest(unittest.TestCase):
    def test_parallel_execution_preserves_order_and_bounds_concurrency(self) -> None:
        registry = ToolRegistry()
        tool = CountingTool()
        registry.register_tool(tool)
        executor = AsyncToolExecutor(registry, max_concurrency=2, timeout=1.0)
        tasks = [
            {"tool_name": "counting", "parameters": {"value": index}}
            for index in range(5)
        ]

        results = asyncio.run(executor.execute_tools_parallel(tasks))

        self.assertEqual(results, ["0", "1", "2", "3", "4"])
        self.assertEqual(tool.maximum_active, 2)

    def test_executes_existing_registry_tools(self) -> None:
        registry = ToolRegistry()
        registry.register_tool(CalculatorTool())
        executor = AsyncToolExecutor(registry)

        results = asyncio.run(
            executor.execute_tools_parallel(
                [
                    {
                        "tool_name": "calculator",
                        "parameters": {"expression": "2 + 2"},
                    },
                    {
                        "tool_name": "calculator",
                        "parameters": {"expression": "3 * 3"},
                    },
                ]
            )
        )

        self.assertEqual(results, ["4", "9"])

    def test_applies_timeout_and_validates_tasks(self) -> None:
        registry = ToolRegistry()
        registry.register_tool(CountingTool(delay=0.03))
        executor = AsyncToolExecutor(registry, timeout=0.001)

        with self.assertRaises(TimeoutError):
            asyncio.run(
                executor.execute_tool_async(
                    "counting",
                    {"value": 1},
                )
            )
        with self.assertRaises(ValueError):
            asyncio.run(executor.execute_tools_parallel([]))
        with self.assertRaises(ValueError):
            AsyncToolExecutor(registry, max_concurrency=0)


if __name__ == "__main__":
    unittest.main()
