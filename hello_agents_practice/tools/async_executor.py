"""Bounded asynchronous execution for synchronous registered tools."""

import asyncio
from collections.abc import Mapping, Sequence
from typing import Any, TypedDict

from .registry import ToolRegistry


MAX_PARALLEL_TASKS = 100


class ToolTask(TypedDict):
    tool_name: str
    parameters: Mapping[str, Any]


class AsyncToolExecutor:
    """Run blocking ToolRegistry calls without blocking the event loop."""

    def __init__(
        self,
        registry: ToolRegistry,
        max_concurrency: int = 4,
        timeout: float = 30.0,
    ) -> None:
        if not isinstance(registry, ToolRegistry):
            raise TypeError("registry must be a ToolRegistry instance.")
        if not 1 <= max_concurrency <= 32:
            raise ValueError("max_concurrency must be between 1 and 32.")
        if timeout <= 0:
            raise ValueError("timeout must be positive.")
        self.registry = registry
        self.timeout = timeout
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def execute_tool_async(
        self,
        tool_name: str,
        parameters: Mapping[str, Any],
    ) -> str:
        if not isinstance(parameters, Mapping):
            raise TypeError("tool parameters must be a mapping.")
        async with self._semaphore:
            operation = asyncio.to_thread(
                self.registry.execute_tool,
                tool_name,
                dict(parameters),
            )
            return await asyncio.wait_for(operation, timeout=self.timeout)

    async def execute_tools_parallel(
        self,
        tasks: Sequence[ToolTask],
    ) -> list[str]:
        if not tasks:
            raise ValueError("parallel execution requires at least one task.")
        if len(tasks) > MAX_PARALLEL_TASKS:
            raise ValueError(
                f"parallel execution supports at most {MAX_PARALLEL_TASKS} tasks."
            )
        normalized: list[tuple[str, Mapping[str, Any]]] = []
        for task in tasks:
            if not isinstance(task, Mapping):
                raise TypeError("each tool task must be a mapping.")
            tool_name = task.get("tool_name")
            parameters = task.get("parameters")
            if not isinstance(tool_name, str) or not tool_name.strip():
                raise ValueError("each tool task requires a non-empty tool_name.")
            if not isinstance(parameters, Mapping):
                raise TypeError("each tool task requires mapping parameters.")
            normalized.append((tool_name, parameters))

        results: list[str | None] = [None] * len(normalized)

        async def run_one(
            index: int,
            tool_name: str,
            parameters: Mapping[str, Any],
        ) -> None:
            results[index] = await self.execute_tool_async(tool_name, parameters)

        async with asyncio.TaskGroup() as group:
            for index, (tool_name, parameters) in enumerate(normalized):
                group.create_task(run_one(index, tool_name, parameters))

        return [result for result in results if result is not None]


__all__ = ["AsyncToolExecutor", "ToolTask"]
