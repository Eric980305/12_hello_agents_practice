"""Explicit registry and dispatch boundary for agent tools."""

from collections.abc import Callable, Mapping
from typing import Any

from .base import Tool
from .function import FunctionTool


class ToolRegistry:
    """Register and execute an allowlisted set of tools."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register_tool(self, tool: Tool) -> None:
        if not isinstance(tool, Tool):
            raise TypeError("tool must implement Tool.")
        name = tool.name.strip()
        if not name:
            raise ValueError("tool name must not be empty.")
        if name in self._tools:
            raise ValueError(f"tool '{name}' is already registered.")
        self._tools[name] = tool

    def register_function(
        self,
        name: str,
        description: str,
        func: Callable[..., Any],
        parameters: dict[str, Any] | None = None,
    ) -> FunctionTool:
        """Adapt and register a callable through the same Tool path."""
        tool = FunctionTool(name, description, func, parameters)
        self.register_tool(tool)
        return tool

    def get_tool(self, name: str) -> Tool | None:
        return self._tools.get(name.strip())

    def execute_tool(self, name: str, parameters: Mapping[str, Any]) -> str:
        tool = self.get_tool(name)
        if tool is None:
            raise KeyError(f"tool '{name}' is not registered.")
        return tool.run(parameters)

    def unregister(self, name: str) -> bool:
        return self._tools.pop(name.strip(), None) is not None

    def list_tools(self) -> list[str]:
        return list(self._tools)

    def get_tools_description(self) -> str:
        if not self._tools:
            return "暂无可用工具"
        return "\n".join(
            f"- {name}: {tool.description}"
            for name, tool in self._tools.items()
        )
