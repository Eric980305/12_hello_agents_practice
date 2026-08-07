import json
import unittest

from hello_agents_framework import MemoryManager, MemoryTool, ToolRegistry


class MemoryToolTest(unittest.TestCase):
    def test_registers_and_runs_the_working_memory_lifecycle(self) -> None:
        registry = ToolRegistry()
        tool = MemoryTool(user_id="user-a")
        registry.register_tool(tool)

        added = registry.execute_tool(
            "memory",
            {
                "action": "add",
                "content": "正在学习 Python 函数",
                "importance": "0.8",
                "metadata": {"topic": "python"},
            },
        )
        memory_id = added.split("id=", 1)[1].split(" ", 1)[0]
        searched = tool.execute("search", query="Python 函数", limit="3")
        updated = tool.execute(
            "update",
            memory_id=memory_id,
            content="正在学习 Python 函数参数",
        )
        stats = json.loads(tool.execute("stats"))

        self.assertIn("正在学习 Python 函数", searched)
        self.assertIn(memory_id, updated)
        self.assertEqual(stats["total_memories"], 1)
        self.assertEqual(registry.list_tools(), ["memory"])
        self.assertIn("action", tool.parameters["required"])

    def test_scopes_shared_manager_operations_by_user(self) -> None:
        manager = MemoryManager()
        first = MemoryTool(user_id="user-a", manager=manager)
        second = MemoryTool(user_id="user-b", manager=manager)
        first.execute("add", content="Alice Python note")
        second.execute("add", content="Bob Python note")

        self.assertIn("Alice", first.execute("search", query="Python"))
        self.assertNotIn("Bob", first.execute("search", query="Python"))
        self.assertEqual(first.execute("clear_all", confirm="true"), "已清空当前用户的 1 条记忆。")
        self.assertIn("Bob", second.execute("search", query="Python"))

    def test_validates_actions_types_and_destructive_confirmation(self) -> None:
        tool = MemoryTool(user_id="user-a")

        with self.assertRaises(ValueError):
            tool.execute("missing")
        with self.assertRaisesRegex(ValueError, "not enabled"):
            tool.execute(
                "add",
                content="persistent fact",
                memory_type="semantic",
            )
        with self.assertRaises(PermissionError):
            tool.execute("clear_all")
        with self.assertRaises(TypeError):
            tool.execute("search", query="Python", limit="many")
        with self.assertRaises(TypeError):
            tool.run("not-a-mapping")


if __name__ == "__main__":
    unittest.main()
