"""Deterministic sequential composition for registered tools."""

import re
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from .registry import ToolRegistry


REFERENCE_PATTERN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


@dataclass(frozen=True)
class ToolChainStep:
    """One registered tool invocation and its named output."""

    tool_name: str
    parameters: dict[str, Any]
    output_key: str


class ToolChain:
    """Execute dependent tools in a fixed, validated order."""

    def __init__(self, name: str, description: str) -> None:
        if not name.strip() or not description.strip():
            raise ValueError("chain name and description must not be empty.")
        self.name = name.strip()
        self.description = description.strip()
        self.steps: list[ToolChainStep] = []

    def add_step(
        self,
        tool_name: str,
        parameters: Mapping[str, Any],
        output_key: str | None = None,
    ) -> None:
        name = tool_name.strip()
        if not name:
            raise ValueError("chain tool name must not be empty.")
        if not isinstance(parameters, Mapping):
            raise TypeError("chain step parameters must be a mapping.")
        key = (output_key or f"step_{len(self.steps) + 1}_result").strip()
        if not key or key == "input":
            raise ValueError("chain output key must be non-empty and cannot be 'input'.")
        if any(step.output_key == key for step in self.steps):
            raise ValueError(f"chain output key '{key}' is already used.")
        self.steps.append(
            ToolChainStep(
                tool_name=name,
                parameters=deepcopy(dict(parameters)),
                output_key=key,
            )
        )

    def execute(
        self,
        registry: ToolRegistry,
        initial_input: Any,
        context: Mapping[str, Any] | None = None,
    ) -> str:
        if not isinstance(registry, ToolRegistry):
            raise TypeError("registry must be a ToolRegistry instance.")
        if not self.steps:
            raise ValueError("tool chain must contain at least one step.")
        missing_tools = [
            step.tool_name
            for step in self.steps
            if registry.get_tool(step.tool_name) is None
        ]
        if missing_tools:
            raise KeyError(f"unregistered chain tool: {missing_tools[0]}.")

        values = dict(context or {})
        values["input"] = initial_input
        for step in self.steps:
            resolved = self._resolve(step.parameters, values)
            result = registry.execute_tool(step.tool_name, resolved)
            values[step.output_key] = result
        return values[self.steps[-1].output_key]

    @classmethod
    def _resolve(cls, value: Any, context: Mapping[str, Any]) -> Any:
        if isinstance(value, str):
            exact = REFERENCE_PATTERN.fullmatch(value)
            if exact:
                return cls._get_context_value(exact.group(1), context)

            def replace(match: re.Match[str]) -> str:
                return str(cls._get_context_value(match.group(1), context))

            return REFERENCE_PATTERN.sub(replace, value)
        if isinstance(value, Mapping):
            return {key: cls._resolve(item, context) for key, item in value.items()}
        if isinstance(value, list):
            return [cls._resolve(item, context) for item in value]
        if isinstance(value, tuple):
            return tuple(cls._resolve(item, context) for item in value)
        return value

    @staticmethod
    def _get_context_value(key: str, context: Mapping[str, Any]) -> Any:
        if key not in context:
            raise ValueError(f"chain context value '{key}' is unavailable.")
        return context[key]


class ToolChainManager:
    """Register named chains that share one ToolRegistry."""

    def __init__(self, registry: ToolRegistry) -> None:
        if not isinstance(registry, ToolRegistry):
            raise TypeError("registry must be a ToolRegistry instance.")
        self.registry = registry
        self._chains: dict[str, ToolChain] = {}

    def register_chain(self, chain: ToolChain) -> None:
        if not isinstance(chain, ToolChain):
            raise TypeError("chain must be a ToolChain instance.")
        if chain.name in self._chains:
            raise ValueError(f"tool chain '{chain.name}' is already registered.")
        self._chains[chain.name] = chain

    def execute_chain(
        self,
        chain_name: str,
        input_data: Any,
        context: Mapping[str, Any] | None = None,
    ) -> str:
        chain = self._chains.get(chain_name.strip())
        if chain is None:
            raise KeyError(f"tool chain '{chain_name}' is not registered.")
        return chain.execute(self.registry, input_data, context)

    def list_chains(self) -> list[str]:
        return list(self._chains)


__all__ = ["ToolChain", "ToolChainManager", "ToolChainStep"]
