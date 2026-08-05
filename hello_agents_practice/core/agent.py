"""Abstract agent contract and shared conversation-history behavior."""

from abc import ABC, abstractmethod
from typing import Any

from .config import Config
from .llm import HelloAgentsLLM
from .message import Message


class Agent(ABC):
    """Define the common interface implemented by every concrete agent."""

    def __init__(
        self,
        name: str,
        llm: HelloAgentsLLM,
        system_prompt: str | None = None,
        config: Config | None = None,
    ) -> None:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("Agent name must not be empty.")

        self.name = normalized_name
        self.llm = llm
        self.system_prompt = system_prompt
        self.config = config if config is not None else Config()
        self._history: list[Message] = []

    @abstractmethod
    def run(self, input_text: str, **kwargs: Any) -> str:
        """Run the agent for one user input."""
        raise NotImplementedError

    def add_message(self, message: Message) -> None:
        """Append one validated message and enforce the history limit."""
        if not isinstance(message, Message):
            raise TypeError("message must be a Message instance.")

        self._history.append(message)
        overflow = len(self._history) - self.config.max_history_length
        if overflow > 0:
            del self._history[:overflow]

    def clear_history(self) -> None:
        """Remove all conversation history."""
        self._history.clear()

    def get_history(self) -> list[Message]:
        """Return a shallow copy so callers cannot replace internal history."""
        return self._history.copy()

    def __str__(self) -> str:
        provider = getattr(self.llm, "provider", self.config.provider)
        return f"Agent(name={self.name}, provider={provider})"
