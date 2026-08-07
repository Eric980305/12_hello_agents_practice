from hello_agents_framework import CalculatorTool, ToolRegistry


def my_calculate(expression: str) -> str:
    """Reuse the safe calculator implementation behind a plain function."""
    return CalculatorTool().run({"expression": expression})


def main() -> None:
    """Demonstrate callable adaptation without an LLM request."""
    registry = ToolRegistry()
    tool = registry.register_function(
        name="my_calculator",
        description="Evaluate a bounded arithmetic expression.",
        func=my_calculate,
    )

    print(f"注册工具：{registry.list_tools()}")
    print(f"参数Schema：{tool.parameters}")
    for expression in ("2 + 3", "10 - 4", "5 * 6", "15 / 3"):
        result = registry.execute_tool(
            "my_calculator",
            {"expression": expression},
        )
        print(f"{expression} = {result}")


if __name__ == "__main__":
    main()
