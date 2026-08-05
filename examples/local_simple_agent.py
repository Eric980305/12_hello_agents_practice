from pathlib import Path

from dotenv import load_dotenv

from hello_agents_practice import CalculatorTool, Config, HelloAgentsLLM, SimpleAgent


ROOT_DIR = Path(__file__).resolve().parents[3]


def create_llm(config: Config) -> HelloAgentsLLM:
    if config.model_id is None or config.api_key is None or config.base_url is None:
        raise RuntimeError("LLM_MODEL_ID, LLM_API_KEY, and LLM_BASE_URL are required.")
    return HelloAgentsLLM(
        model=config.model_id,
        api_key=config.api_key.get_secret_value(),
        base_url=config.base_url,
    )


def main() -> None:
    """Run the local Chapter 7 SimpleAgent implementation."""
    load_dotenv(ROOT_DIR / ".env", override=False)
    config = Config.from_env()
    llm = create_llm(config)

    basic_agent = SimpleAgent(
        name="基础助手",
        llm=llm,
        system_prompt="你是一个友好的AI助手，请简洁回答。",
        config=config,
    )
    print(basic_agent.run("你好，请介绍一下自己。"))

    tool_agent = SimpleAgent(
        name="计算助手",
        llm=llm,
        system_prompt="需要精确计算时使用已注册的计算器。",
        config=config,
    )
    tool_agent.add_tool(CalculatorTool())
    print(tool_agent.run("请计算 15 * 8 + 32。"))

    print("流式响应：", end="")
    for chunk in basic_agent.stream_run("用一句话解释人工智能。"):
        print(chunk, end="", flush=True)
    print()
    print(f"历史消息数：{len(basic_agent.get_history())}")


if __name__ == "__main__":
    main()
