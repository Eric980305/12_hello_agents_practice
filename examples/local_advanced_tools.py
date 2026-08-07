import asyncio

from hello_agents_framework import (
    AsyncToolExecutor,
    CalculatorTool,
    ToolChain,
    ToolChainManager,
    ToolRegistry,
)


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register_tool(CalculatorTool())
    return registry


def run_chain(registry: ToolRegistry) -> None:
    chain = ToolChain(
        name="calculate_then_double",
        description="Calculate an expression and double its result.",
    )
    chain.add_step(
        "calculator",
        {"expression": "{input}"},
        output_key="calculation",
    )
    chain.add_step(
        "calculator",
        {"expression": "{calculation} * 2"},
        output_key="doubled",
    )
    manager = ToolChainManager(registry)
    manager.register_chain(chain)
    result = manager.execute_chain("calculate_then_double", "2 + 3")
    print(f"Chain result: {result}")


async def run_parallel(registry: ToolRegistry) -> None:
    executor = AsyncToolExecutor(registry, max_concurrency=2)
    results = await executor.execute_tools_parallel(
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
    print(f"Parallel results: {results}")


def main() -> None:
    registry = build_registry()
    run_chain(registry)
    asyncio.run(run_parallel(registry))


if __name__ == "__main__":
    main()
