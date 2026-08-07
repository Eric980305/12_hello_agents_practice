from dotenv import load_dotenv

from examples.local_simple_agent import ROOT_DIR, create_llm
from hello_agents_framework import (
    CalculatorTool,
    Config,
    FunctionCallAgent,
    ToolRegistry,
)


def main() -> None:
    """Check native tool calling on the configured OpenAI-compatible provider."""
    load_dotenv(ROOT_DIR / ".env", override=False)
    config = Config.from_env()
    registry = ToolRegistry()
    registry.register_tool(CalculatorTool())
    agent = FunctionCallAgent(
        name="原生函数调用助手",
        llm=create_llm(config),
        tool_registry=registry,
        config=config,
        system_prompt="需要精确计算时必须使用已提供的工具。",
    )

    answer = agent.run("请计算 15 * 8 + 32，并说明结果。")
    print("工具调用记录：")
    for record in agent.current_tool_calls:
        print(record)
    print(f"最终答案：{answer}")


if __name__ == "__main__":
    main()
