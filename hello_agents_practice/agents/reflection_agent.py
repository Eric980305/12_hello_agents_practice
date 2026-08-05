"""Task-generic, bounded reflection agent."""

from collections.abc import Mapping
from string import Formatter
from typing import Any, Literal, TypedDict

from ..core.agent import Agent
from ..core.config import Config
from ..core.llm import HelloAgentsLLM
from ..core.message import Message


DEFAULT_PROMPTS = {
    "initial": """请根据以下要求完成任务：

任务：{task}

请提供一个完整、准确的回答。""",
    "reflect": """请仔细审查以下回答，并找出可能的问题或改进空间：

# 原始任务
{task}

# 当前回答
{content}

请分析回答的质量，指出不足并提出具体改进建议。如果回答已经很好，只回答“无需改进”。""",
    "refine": """请根据反馈意见改进回答：

# 原始任务
{task}

# 上一轮回答
{last_attempt}

# 反馈意见
{feedback}

请提供改进后的完整回答。""",
}

PROMPT_FIELDS = {
    "initial": {"task"},
    "reflect": {"task", "content"},
    "refine": {"task", "last_attempt", "feedback"},
}
MAX_REFLECTION_ITERATIONS = 10
TrajectoryStage = Literal["initial", "reflection", "refinement"]


class TrajectoryRecord(TypedDict):
    stage: TrajectoryStage
    content: str


class ReflectionAgent(Agent):
    """Generate, review, and revise one answer within a fixed budget."""

    def __init__(
        self,
        name: str,
        llm: HelloAgentsLLM,
        system_prompt: str | None = None,
        config: Config | None = None,
        max_iterations: int = 3,
        custom_prompts: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(name, llm, system_prompt, config)
        if not 1 <= max_iterations <= MAX_REFLECTION_ITERATIONS:
            raise ValueError(
                "max_iterations must be between "
                f"1 and {MAX_REFLECTION_ITERATIONS}."
            )

        self.max_iterations = max_iterations
        self.prompts = self._build_prompts(custom_prompts)
        self.current_trajectory: list[TrajectoryRecord] = []

    def run(self, input_text: str, **kwargs: Any) -> str:
        """Run a fresh initial-review-refine trajectory for one task."""
        task = input_text.strip()
        if not task:
            raise ValueError("input_text must not be empty.")

        self.current_trajectory = []
        current_answer = self._invoke(
            self.prompts["initial"].format(task=task),
            **kwargs,
        )
        self._record("initial", current_answer)

        for _ in range(self.max_iterations):
            feedback = self._invoke(
                self.prompts["reflect"].format(
                    task=task,
                    content=current_answer,
                ),
                **kwargs,
            )
            self._record("reflection", feedback)
            if self._is_accepted(feedback):
                return self._finish(task, current_answer)

            current_answer = self._invoke(
                self.prompts["refine"].format(
                    task=task,
                    last_attempt=current_answer,
                    feedback=feedback,
                ),
                **kwargs,
            )
            self._record("refinement", current_answer)

        return self._finish(task, current_answer)

    def _invoke(self, prompt: str, **kwargs: Any) -> str:
        messages: list[dict[str, str]] = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.append({"role": "user", "content": prompt})
        return self.llm.invoke(messages, **kwargs)

    def _record(self, stage: TrajectoryStage, content: str) -> None:
        self.current_trajectory.append({"stage": stage, "content": content})

    @staticmethod
    def _is_accepted(feedback: str) -> bool:
        normalized = feedback.strip().rstrip("。.!！").strip()
        return normalized == "无需改进"

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

    def _finish(self, task: str, answer: str) -> str:
        self.add_message(Message(content=task, role="user"))
        self.add_message(Message(content=answer, role="assistant"))
        return answer


__all__ = ["DEFAULT_PROMPTS", "ReflectionAgent", "TrajectoryRecord"]
