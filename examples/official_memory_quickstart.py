"""Experience the official HelloAgents 0.2.0 memory tool.

Run from ``projects/12_hello_agents_framework`` after starting the local
Qdrant and Neo4j services. The example calls MemoryTool directly, so it uses
the embedding and storage services but does not send a chat request to the LLM.
"""

from __future__ import annotations

from examples.official_memory_rag_quickstart import configure_environment


def require_success(label: str, result: str, expected_text: str | None = None) -> None:
    """Reject an unsuccessful tool result while keeping the example readable."""
    if result.startswith(("❌", "⚠️")):
        raise RuntimeError(f"{label} failed: {result}")
    if expected_text is not None and expected_text not in result:
        raise RuntimeError(f"{label} returned no expected evidence")
    print(result)


def main() -> None:
    configure_environment()

    # Import after loading the environment because HelloAgents 0.2.0 captures
    # its database configuration while the memory modules are imported.
    from hello_agents import HelloAgentsLLM, SimpleAgent, ToolRegistry
    from hello_agents.tools import MemoryTool

    llm = HelloAgentsLLM(provider="auto")
    agent = SimpleAgent(name="MemoryAssistant", llm=llm)

    memory_tool = MemoryTool(user_id="user123")
    tool_registry = ToolRegistry()
    tool_registry.register_tool(memory_tool)
    agent.tool_registry = tool_registry

    print("=== Add semantic memories ===")
    memories = [
        ("张三是一名 Python 开发者，专注于机器学习和数据分析。", 0.8),
        ("李四是前端工程师，擅长 React 和 Vue.js 开发。", 0.7),
        ("王五是产品经理，负责用户体验设计和需求分析。", 0.6),
    ]
    for index, (content, importance) in enumerate(memories, 1):
        result = memory_tool.execute(
            "add",
            content=content,
            memory_type="semantic",
            importance=importance,
        )
        print(f"Memory {index}: ", end="")
        require_success(f"semantic memory {index}", result)

    print("\n=== Search memories ===")
    result = memory_tool.execute(
        "search",
        query="前端工程师",
        memory_type="semantic",
        limit=3,
    )
    require_success("semantic memory search", result, "李四")

    print("\n=== Memory summary ===")
    result = memory_tool.execute("summary")
    require_success("memory summary", result)

    print("\n[OK] Official HelloAgents memory quickstart completed")


if __name__ == "__main__":
    main()
