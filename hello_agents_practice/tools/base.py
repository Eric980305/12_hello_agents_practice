"""Minimal contract for tools callable by agents."""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any


class Tool(ABC):
    """Expose one named, described, validated operation to an agent."""

    name: str
    description: str

    @property
    def parameters(self) -> dict[str, Any]:
        """Return the default single-input JSON schema for native tool calls."""
        return {
            "type": "object",
            "properties": {
                "input": {
                    "type": "string",
                    "description": "Input passed to the tool.",
                }
            },
            "required": ["input"],
            "additionalProperties": False,
        }

    @abstractmethod
    def run(self, parameters: Mapping[str, Any]) -> str:
        """Execute the tool with validated parameters."""
        raise NotImplementedError
