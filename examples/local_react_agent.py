from dotenv import load_dotenv

from examples.local_simple_agent import ROOT_DIR, create_llm
from hello_agents_framework import CalculatorTool, Config, ReActAgent, ToolRegistry


def main() -> None:
    """Run the local ReActAgent through a real LLM and registered tool."""
    load_dotenv(ROOT_DIR / ".env", override=False)
    config = Config.from_env()
    registry = ToolRegistry()
    registry.register_tool(CalculatorTool())

    agent = ReActAgent(
        name="ReAct计算助手",
        llm=create_llm(config),
        tool_registry=registry,
        config=config,
        max_steps=5,
    )
    answer = agent.run("请使用 calculator 工具计算 15 * 8 + 32，并给出结果。")

    print("执行轨迹：")
    for event in agent.current_history:
        print(event)
    print(f"最终答案：{answer}")


if __name__ == "__main__":
    main()
