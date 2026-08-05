"""Validated configuration loaded from the process environment."""

import os
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr


LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class Config(BaseModel):
    """Configure the framework without assuming a specific model provider."""

    model_config = ConfigDict(extra="forbid")

    model_id: str | None = Field(default=None, min_length=1)
    provider: str = Field(default="auto", min_length=1)
    api_key: SecretStr | None = Field(default=None, repr=False)
    base_url: str | None = Field(default=None, min_length=1)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, gt=0)
    timeout: float = Field(default=60.0, gt=0)

    debug: bool = False
    log_level: LogLevel = "INFO"
    max_history_length: int = Field(default=100, gt=0)

    @classmethod
    def from_env(cls) -> "Config":
        """Create configuration from already-loaded environment variables."""
        values: dict[str, str | None] = {
            "model_id": os.getenv("LLM_MODEL_ID"),
            "provider": os.getenv("LLM_PROVIDER"),
            "api_key": os.getenv("LLM_API_KEY"),
            "base_url": os.getenv("LLM_BASE_URL"),
            "temperature": os.getenv("LLM_TEMPERATURE"),
            "max_tokens": os.getenv("LLM_MAX_TOKENS"),
            "timeout": os.getenv("LLM_TIMEOUT"),
            "debug": os.getenv("DEBUG"),
            "log_level": (
                os.getenv("LOG_LEVEL", "").upper() or None
            ),
            "max_history_length": os.getenv("MAX_HISTORY_LENGTH"),
        }
        return cls(**{key: value for key, value in values.items() if value is not None})

    def to_dict(self) -> dict[str, Any]:
        """Return a serializable configuration view without credentials."""
        return self.model_dump(exclude={"api_key"})
