"""User-scoped MemoryTool facade for the practice framework."""

from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
from typing import Any, Callable, cast
from uuid import uuid4

from ...memory import ForgetStrategy, MemoryConfig, MemoryManager, MemoryType
from ..base import Tool


class MemoryTool(Tool):
    """Expose validated memory lifecycle actions through one registered tool."""

    name = "memory"
    description = "Store, search, update, forget, and summarize user-scoped memory."

    _parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "add",
                    "search",
                    "summary",
                    "stats",
                    "update",
                    "remove",
                    "forget",
                    "clear_all",
                ],
                "description": "Memory operation to execute.",
            },
            "content": {"type": "string", "description": "Memory content."},
            "query": {"type": "string", "description": "Memory search query."},
            "memory_type": {
                "type": "string",
                "enum": ["working", "episodic", "semantic", "perceptual"],
                "description": "Target memory type; availability depends on the configured manager.",
            },
            "memory_types": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["working", "episodic", "semantic", "perceptual"],
                },
                "description": "Memory types included in a search.",
            },
            "importance": {
                "type": "number",
                "description": "Importance from 0.0 to 1.0.",
            },
            "metadata": {
                "type": "object",
                "description": "Structured context stored with the memory.",
            },
            "ttl_seconds": {
                "type": "integer",
                "description": "Working-memory lifetime in seconds.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum search result count.",
            },
            "min_importance": {
                "type": "number",
                "description": "Minimum importance accepted by search.",
            },
            "memory_id": {
                "type": "string",
                "description": "Memory identifier for update or removal.",
            },
            "strategy": {
                "type": "string",
                "enum": ["importance_based", "time_based", "capacity_based"],
                "description": "Forgetting strategy.",
            },
            "threshold": {
                "type": "number",
                "description": "Importance threshold used by forgetting.",
            },
            "max_age_days": {
                "type": "integer",
                "description": "Maximum record age used by time-based forgetting.",
            },
            "confirm": {
                "type": "boolean",
                "description": "Must be true for destructive clear_all.",
            },
        },
        "required": ["action"],
        "additionalProperties": False,
    }

    def __init__(
        self,
        user_id: str,
        *,
        manager: MemoryManager | None = None,
        config: MemoryConfig | None = None,
        session_id: str | None = None,
    ) -> None:
        normalized_user_id = self._required_text(user_id, "user_id")
        if manager is not None and config is not None:
            raise ValueError("pass manager or config, not both.")
        self.user_id = normalized_user_id
        self.manager = manager or MemoryManager(config=config)
        self.session_id = session_id or f"session_{uuid4().hex}"

    @property
    def parameters(self) -> dict[str, Any]:
        return deepcopy(self._parameters)

    def run(self, parameters: Mapping[str, Any]) -> str:
        if not isinstance(parameters, Mapping):
            raise TypeError("memory tool parameters must be a mapping.")
        values = dict(parameters)
        action = values.pop("action", None)
        return self.execute(action, **values)

    def execute(self, action: Any, **kwargs: Any) -> str:
        normalized_action = self._required_text(action, "action")
        handlers: dict[str, Callable[..., str]] = {
            "add": self._add_memory,
            "search": self._search_memory,
            "summary": self._get_summary,
            "stats": self._get_stats,
            "update": self._update_memory,
            "remove": self._remove_memory,
            "forget": self._forget,
            "clear_all": self._clear_all,
        }
        try:
            handler = handlers[normalized_action]
        except KeyError as error:
            raise ValueError(f"unsupported memory action: {normalized_action}") from error
        return handler(**kwargs)

    def _add_memory(
        self,
        *,
        content: Any,
        memory_type: Any = "working",
        importance: Any = 0.5,
        metadata: Any = None,
        ttl_seconds: Any = None,
    ) -> str:
        normalized_type = self._memory_type(memory_type)
        context = self._mapping(metadata, "metadata")
        context.setdefault("session_id", self.session_id)
        item = self.manager.add_memory(
            user_id=self.user_id,
            content=self._required_text(content, "content"),
            memory_type=normalized_type,
            importance=self._float(importance, "importance", minimum=0.0, maximum=1.0),
            metadata=context,
            ttl_seconds=(
                None
                if ttl_seconds is None
                else self._integer(ttl_seconds, "ttl_seconds", minimum=1)
            ),
        )
        return f"记忆已添加：id={item.id} type={item.memory_type}"

    def _search_memory(
        self,
        *,
        query: Any,
        memory_type: Any = None,
        memory_types: Any = None,
        limit: Any = 5,
        min_importance: Any = 0.0,
    ) -> str:
        if memory_type is not None and memory_types is not None:
            raise ValueError("pass memory_type or memory_types, not both.")
        selected = None
        if memory_types is not None:
            if not isinstance(memory_types, list) or not memory_types:
                raise TypeError("memory_types must be a non-empty list.")
            selected = [self._memory_type(value) for value in memory_types]
        elif memory_type is not None:
            selected = [self._memory_type(memory_type)]

        results = self.manager.retrieve_memories(
            user_id=self.user_id,
            query=self._required_text(query, "query"),
            memory_types=selected,
            limit=self._integer(limit, "limit", minimum=1, maximum=100),
            min_importance=self._float(
                min_importance,
                "min_importance",
                minimum=0.0,
                maximum=1.0,
            ),
        )
        if not results:
            return "未找到相关记忆。"
        lines = [f"找到 {len(results)} 条相关记忆："]
        lines.extend(
            f"{index}. [{result.memory.memory_type}] {result.memory.content} "
            f"(score={result.score:.3f}, importance={result.memory.importance:.2f}, "
            f"id={result.memory.id})"
            for index, result in enumerate(results, 1)
        )
        return "\n".join(lines)

    def _get_summary(self) -> str:
        stats = self.manager.get_memory_stats(user_id=self.user_id)
        lines = [
            "记忆摘要：",
            f"用户：{self.user_id}",
            f"总数：{stats['total_memories']}",
        ]
        lines.extend(
            f"- {memory_type}: {values['count']} 条，"
            f"平均重要性 {values['average_importance']:.2f}"
            for memory_type, values in stats["memories_by_type"].items()
        )
        return "\n".join(lines)

    def _get_stats(self) -> str:
        return json.dumps(
            self.manager.get_memory_stats(user_id=self.user_id),
            ensure_ascii=False,
            sort_keys=True,
        )

    def _update_memory(
        self,
        *,
        memory_id: Any,
        content: Any = None,
        importance: Any = None,
        metadata: Any = None,
    ) -> str:
        item = self.manager.update_memory(
            user_id=self.user_id,
            memory_id=self._required_text(memory_id, "memory_id"),
            content=(None if content is None else self._required_text(content, "content")),
            importance=(
                None
                if importance is None
                else self._float(importance, "importance", minimum=0.0, maximum=1.0)
            ),
            metadata=(None if metadata is None else self._mapping(metadata, "metadata")),
        )
        return f"记忆已更新：id={item.id}"

    def _remove_memory(self, *, memory_id: Any) -> str:
        removed = self.manager.remove_memory(
            user_id=self.user_id,
            memory_id=self._required_text(memory_id, "memory_id"),
        )
        if not removed:
            raise KeyError("memory was not found for this user.")
        return "记忆已删除。"

    def _forget(
        self,
        *,
        strategy: Any = "importance_based",
        threshold: Any = 0.1,
        max_age_days: Any = 30,
    ) -> str:
        normalized_strategy = self._required_text(strategy, "strategy")
        allowed = {"importance_based", "time_based", "capacity_based"}
        if normalized_strategy not in allowed:
            raise ValueError(f"unsupported forgetting strategy: {normalized_strategy}")
        count = self.manager.forget_memories(
            user_id=self.user_id,
            strategy=cast(ForgetStrategy, normalized_strategy),
            threshold=self._float(
                threshold,
                "threshold",
                minimum=0.0,
                maximum=1.0,
            ),
            max_age_days=self._integer(
                max_age_days,
                "max_age_days",
                minimum=1,
            ),
        )
        return f"已遗忘 {count} 条记忆。"

    def _clear_all(self, *, confirm: Any = False) -> str:
        if not self._boolean(confirm, "confirm"):
            raise PermissionError("clear_all requires confirm=true.")
        count = self.manager.clear_memories(user_id=self.user_id)
        return f"已清空当前用户的 {count} 条记忆。"

    @staticmethod
    def _required_text(value: Any, name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string.")
        return value.strip()

    @staticmethod
    def _mapping(value: Any, name: str) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            raise TypeError(f"{name} must be an object.")
        return dict(value)

    @classmethod
    def _memory_type(cls, value: Any) -> MemoryType:
        normalized = cls._required_text(value, "memory_type")
        allowed = {"working", "episodic", "semantic", "perceptual"}
        if normalized not in allowed:
            raise ValueError(f"unsupported memory type: {normalized}")
        return cast(MemoryType, normalized)

    @staticmethod
    def _integer(
        value: Any,
        name: str,
        *,
        minimum: int,
        maximum: int | None = None,
    ) -> int:
        if isinstance(value, bool):
            raise TypeError(f"{name} must be an integer.")
        try:
            converted = int(value)
        except (TypeError, ValueError) as error:
            raise TypeError(f"{name} must be an integer.") from error
        if isinstance(value, float) and not value.is_integer():
            raise TypeError(f"{name} must be an integer.")
        if converted < minimum or (maximum is not None and converted > maximum):
            raise ValueError(f"{name} is outside the allowed range.")
        return converted

    @staticmethod
    def _float(
        value: Any,
        name: str,
        *,
        minimum: float,
        maximum: float,
    ) -> float:
        if isinstance(value, bool):
            raise TypeError(f"{name} must be a number.")
        try:
            converted = float(value)
        except (TypeError, ValueError) as error:
            raise TypeError(f"{name} must be a number.") from error
        if not minimum <= converted <= maximum:
            raise ValueError(f"{name} is outside the allowed range.")
        return converted

    @staticmethod
    def _boolean(value: Any, name: str) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip().casefold() in {"true", "false"}:
            return value.strip().casefold() == "true"
        raise TypeError(f"{name} must be a boolean.")


__all__ = ["MemoryTool"]
