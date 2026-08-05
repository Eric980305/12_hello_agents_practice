"""Message primitives shared by framework components."""

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


MessageRole = Literal["user", "assistant", "system", "tool"]


def utc_now() -> datetime:
    """Return an aware UTC timestamp for portable logs and serialization."""
    return datetime.now(timezone.utc)


class Message(BaseModel):
    """Represent one internal conversation message."""

    content: str
    role: MessageRole
    timestamp: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, str]:
        """Return the role and content accepted by OpenAI-compatible APIs."""
        return {"role": self.role, "content": self.content}

    def __str__(self) -> str:
        return f"[{self.role}] {self.content}"
