import argparse

from dotenv import load_dotenv

from examples.local_simple_agent import ROOT_DIR, create_llm
from hello_agents_framework import Config, PlanAndSolveAgent


MATH_PROMPTS = {
    "planner": """你是数学问题规划专家。请将问题分解为不超过 {max_steps} 个计算步骤。
问题：{question}
只输出Python字符串列表，例如：["计算步骤1", "计算步骤2", "求总和"]""",
    "executor": """你是数学计算专家。请只完成当前步骤。
问题：{question}
计划：{plan}
历史：{history}
当前步骤：{current_step}
请只输出当前步骤的计算结果。""",
}

QUESTION = (
    "一个水果店周一卖出了15个苹果。周二卖出的苹果数量是周一的两倍。"
    "周三卖出的数量比周二少了5个。请问这三天总共卖出了多少个苹果？"
)


def main() -> None:
    """Run one real-model Plan-and-Solve scenario."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("default", "math"), default="default")
    args = parser.parse_args()

    load_dotenv(ROOT_DIR / ".env", override=False)
    config = Config.from_env()
    agent = PlanAndSolveAgent(
        name="规划执行助手",
        llm=create_llm(config),
        config=config,
        max_steps=6,
        custom_prompts=MATH_PROMPTS if args.mode == "math" else None,
    )

    answer = agent.run(QUESTION)
    print("执行计划：")
    for step in agent.current_plan:
        print(
            f"{step.index}. [{step.status}] {step.description}\n"
            f"   result={step.output or '-'} error={step.error or '-'}"
        )
    print(f"最终结果：{answer}")
    print(f"对话历史：{len(agent.get_history())} 条消息")


if __name__ == "__main__":
    main()
