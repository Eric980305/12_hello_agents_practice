import argparse

from dotenv import load_dotenv

from examples.local_simple_agent import ROOT_DIR, create_llm
from hello_agents_framework import Config, ReflectionAgent


CODE_PROMPTS = {
    "initial": "你是Python专家，请编写函数：{task}",
    "reflect": "请审查代码的算法效率：\n任务：{task}\n代码：{content}",
    "refine": "请根据反馈优化代码：\n任务：{task}\n反馈：{feedback}",
}


def main() -> None:
    """Run one real-model Reflection scenario."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("general", "code"), default="general")
    args = parser.parse_args()

    load_dotenv(ROOT_DIR / ".env", override=False)
    config = Config.from_env()
    llm = create_llm(config)

    if args.mode == "code":
        agent = ReflectionAgent(
            name="代码反思助手",
            llm=llm,
            config=config,
            custom_prompts=CODE_PROMPTS,
        )
        task = "编写一个返回前 n 个斐波那契数的 Python 函数。"
    else:
        agent = ReflectionAgent(name="通用反思助手", llm=llm, config=config)
        task = "写一篇关于人工智能发展历程的简短文章。"

    answer = agent.run(task)
    print("执行轨迹：")
    for record in agent.current_trajectory:
        print(f"[{record['stage']}]\n{record['content']}\n")
    print(f"最终结果：\n{answer}")


if __name__ == "__main__":
    main()
