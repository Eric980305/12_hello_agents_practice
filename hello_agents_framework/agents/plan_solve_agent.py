"""Bounded Plan-and-Solve agent with explicit step state."""

import ast
import re
from collections.abc import Mapping
from dataclasses import dataclass
from string import Formatter
from typing import Any, Literal

from ..core.agent import Agent
from ..core.config import Config
from ..core.llm import HelloAgentsLLM
from ..core.message import Message


DEFAULT_PLANNER_PROMPT = """你是一个AI规划专家。请将用户问题分解成有序、独立、可执行的简单步骤。
计划不得超过 {max_steps} 步。只输出一个Python字符串列表，并保留代码围栏。

问题：{question}

输出格式：
```python
["步骤1", "步骤2", "步骤3"]
```"""

DEFAULT_EXECUTOR_PROMPT = """你是一个AI执行专家。请依据原始问题、完整计划和已完成步骤，只解决当前步骤。
不要提前执行其他步骤，只输出当前步骤的结果。

# 原始问题
{question}

# 完整计划
{plan}

# 历史步骤与结果
{history}

# 当前步骤
{current_step}"""

DEFAULT_SYNTHESIZER_PROMPT = """请根据原始问题、完整计划和全部已完成步骤生成最终答案。
只能使用给定结果；结果冲突或不足时必须明确说明。

# 原始问题
{question}

# 完整计划
{plan}

# 步骤结果
{results}

请直接输出最终答案。"""

DEFAULT_PROMPTS = {
    "planner": DEFAULT_PLANNER_PROMPT,
    "executor": DEFAULT_EXECUTOR_PROMPT,
    "synthesizer": DEFAULT_SYNTHESIZER_PROMPT,
}
PROMPT_FIELDS = {
    "planner": {"question", "max_steps"},
    "executor": {"question", "plan", "history", "current_step"},
    "synthesizer": {"question", "plan", "results"},
}
PLAN_BLOCK_PATTERN = re.compile(r"```(?:python)?\s*(.*?)\s*```", re.DOTALL)
MAX_PLAN_STEPS = 20
MAX_PLAN_TEXT_LENGTH = 10_000
MAX_STEP_TEXT_LENGTH = 500
StepStatus = Literal["pending", "in_progress", "completed", "failed"]


@dataclass
class PlanStep:
    index: int
    description: str
    status: StepStatus = "pending"
    output: str = ""
    error: str = ""


class PlanAndSolveAgent(Agent):
    """Plan globally, solve sequentially, then synthesize once."""

    def __init__(
        self,
        name: str,
        llm: HelloAgentsLLM,
        system_prompt: str | None = None,
        config: Config | None = None,
        max_steps: int = 8,
        custom_prompts: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(name, llm, system_prompt, config)
        if not 1 <= max_steps <= MAX_PLAN_STEPS:
            raise ValueError(f"max_steps must be between 1 and {MAX_PLAN_STEPS}.")

        self.max_steps = max_steps
        self.prompts = self._build_prompts(custom_prompts)
        self.current_plan: list[PlanStep] = []

    def run(self, input_text: str, **kwargs: Any) -> str:
        """Run one fresh plan, sequential execution, and synthesis workflow."""
        question = input_text.strip()
        if not question:
            raise ValueError("input_text must not be empty.")

        self.current_plan = []
        plan_response, error = self._invoke(
            self.prompts["planner"].format(
                question=question,
                max_steps=self.max_steps,
            ),
            **kwargs,
        )
        if error is not None or plan_response is None:
            return self._finish(question, "抱歉，无法生成有效的行动计划。")

        plan = self._parse_plan(plan_response)
        if plan is None:
            return self._finish(question, "抱歉，无法生成有效的行动计划。")
        self.current_plan = [
            PlanStep(index=index, description=description)
            for index, description in enumerate(plan, start=1)
        ]

        for step in self.current_plan:
            step.status = "in_progress"
            output, error = self._invoke(
                self.prompts["executor"].format(
                    question=question,
                    plan=self._format_plan(),
                    history=self._format_results(),
                    current_step=step.description,
                ),
                **kwargs,
            )
            if error is not None or output is None:
                step.status = "failed"
                step.error = error or "EmptyResponse"
                return self._finish(
                    question,
                    "抱歉，计划执行失败，未生成最终答案。",
                )
            step.output = output
            step.status = "completed"

        final_answer, error = self._invoke(
            self.prompts["synthesizer"].format(
                question=question,
                plan=self._format_plan(),
                results=self._format_results(),
            ),
            **kwargs,
        )
        if error is not None or final_answer is None:
            return self._finish(question, "抱歉，最终答案生成失败。")
        return self._finish(question, final_answer)

    def _invoke(self, prompt: str, **kwargs: Any) -> tuple[str | None, str | None]:
        messages: list[dict[str, str]] = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.append({"role": "user", "content": prompt})
        try:
            response = self.llm.invoke(messages, **kwargs)
        except Exception as error:
            return None, type(error).__name__
        if not isinstance(response, str) or not response.strip():
            return None, "EmptyResponse"
        return response.strip(), None

    def _parse_plan(self, response: str) -> list[str] | None:
        match = PLAN_BLOCK_PATTERN.search(response)
        plan_text = (match.group(1) if match else response).strip()
        if not plan_text or len(plan_text) > MAX_PLAN_TEXT_LENGTH:
            return None
        try:
            parsed = ast.literal_eval(plan_text)
        except (SyntaxError, ValueError, MemoryError, RecursionError):
            return None
        if not isinstance(parsed, list) or not 1 <= len(parsed) <= self.max_steps:
            return None
        if any(
            not isinstance(step, str)
            or not step.strip()
            or len(step.strip()) > MAX_STEP_TEXT_LENGTH
            for step in parsed
        ):
            return None
        return [step.strip() for step in parsed]

    def _format_plan(self) -> str:
        return "\n".join(
            f"{step.index}. {step.description}" for step in self.current_plan
        )

    def _format_results(self) -> str:
        completed = [step for step in self.current_plan if step.status == "completed"]
        if not completed:
            return "无"
        return "\n\n".join(
            f"步骤 {step.index}：{step.description}\n结果：{step.output}"
            for step in completed
        )

    @staticmethod
    def _build_prompts(
        custom_prompts: Mapping[str, str] | None,
    ) -> dict[str, str]:
        prompts = dict(DEFAULT_PROMPTS)
        if custom_prompts is None:
            return prompts
        if not isinstance(custom_prompts, Mapping):
            raise TypeError("custom_prompts must be a mapping.")

        unknown_stages = set(custom_prompts) - set(DEFAULT_PROMPTS)
        if unknown_stages:
            unknown = ", ".join(sorted(unknown_stages))
            raise ValueError(f"unknown prompt stages: {unknown}.")

        for stage, template in custom_prompts.items():
            if not isinstance(template, str) or not template.strip():
                raise ValueError(f"prompt '{stage}' must be a non-empty string.")
            try:
                fields = {
                    field_name
                    for _, field_name, _, _ in Formatter().parse(template)
                    if field_name is not None
                }
            except ValueError as error:
                raise ValueError(f"prompt '{stage}' has invalid braces.") from error
            unsupported_fields = fields - PROMPT_FIELDS[stage]
            if unsupported_fields:
                unsupported = ", ".join(sorted(unsupported_fields))
                raise ValueError(
                    f"prompt '{stage}' has unsupported fields: {unsupported}."
                )
            prompts[stage] = template.strip()
        return prompts

    def _finish(self, question: str, answer: str) -> str:
        self.add_message(Message(content=question, role="user"))
        self.add_message(Message(content=answer, role="assistant"))
        return answer


__all__ = [
    "DEFAULT_EXECUTOR_PROMPT",
    "DEFAULT_PLANNER_PROMPT",
    "DEFAULT_SYNTHESIZER_PROMPT",
    "PlanAndSolveAgent",
    "PlanStep",
]
