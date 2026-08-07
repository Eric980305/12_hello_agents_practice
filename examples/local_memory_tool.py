"""Run the practice framework's offline Working Memory example."""

from hello_agents_framework import MemoryTool, ToolRegistry


def main() -> None:
    registry = ToolRegistry()
    registry.register_tool(MemoryTool(user_id="local_demo_user"))

    print("=== Add Working Memory ===")
    print(
        registry.execute_tool(
            "memory",
            {
                "action": "add",
                "content": "用户正在学习 Python 函数。",
                "memory_type": "working",
                "importance": 0.8,
                "metadata": {"topic": "python"},
            },
        )
    )
    print(
        registry.execute_tool(
            "memory",
            {
                "action": "add",
                "content": "下一步需要理解函数参数。",
                "memory_type": "working",
                "importance": 0.7,
            },
        )
    )

    print("\n=== Search Working Memory ===")
    print(
        registry.execute_tool(
            "memory",
            {"action": "search", "query": "Python 函数", "limit": 3},
        )
    )

    print("\n=== Summary ===")
    print(registry.execute_tool("memory", {"action": "summary"}))


if __name__ == "__main__":
    main()
