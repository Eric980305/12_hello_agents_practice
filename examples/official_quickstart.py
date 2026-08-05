from pathlib import Path

from dotenv import load_dotenv
from hello_agents import HelloAgentsLLM, SimpleAgent
from hello_agents.tools import CalculatorTool


ROOT_DIR = Path(__file__).resolve().parents[3]


def main() -> None:
    """Run the official HelloAgents 0.2.0 quickstart example."""
    load_dotenv(ROOT_DIR / ".env", override=False)

    llm = HelloAgentsLLM()
    agent = SimpleAgent(
        name="AI助手",
        llm=llm,
        system_prompt="你是一个有用的AI助手",
    )

    response = agent.run("你好！请介绍一下自己")
    print(response)

    calculator = CalculatorTool()
    # Tool registration is introduced later in section 7.4.1.
    # agent.add_tool(calculator)
    _ = calculator

    response = agent.run("请帮我计算 2 + 3 * 4")
    print(response)
    print(f"历史消息数: {len(agent.get_history())}")

    # messages = [{"role": "user", "content": "你好！"}]
    # for chunk in llm.think(messages):
    #     print(chunk, end="")

if __name__ == "__main__":
    main()
