"""Adapt ordinary Python callables to the unified Tool contract."""

import inspect
from collections.abc import Callable, Mapping
from copy import deepcopy
from typing import Any, get_origin

from .base import Tool


JSON_TYPES: dict[Any, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


class FunctionTool(Tool):
    """Wrap one validated callable without creating a second registry path."""

    def __init__(
        self,
        name: str,
        description: str,
        func: Callable[..., Any],
        parameters: dict[str, Any] | None = None,
    ) -> None:
        if not name.strip():
            raise ValueError("function tool name must not be empty.")
        if not description.strip():
            raise ValueError("function tool description must not be empty.")
        if not callable(func):
            raise TypeError("func must be callable.")

        self.name = name.strip()
        self.description = description.strip()
        self.func = func
        self._signature = inspect.signature(func)
        self._validate_signature()
        self._parameters = (
            self._validate_schema(parameters)
            if parameters is not None
            else self._infer_schema()
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return deepcopy(self._parameters)

    def run(self, parameters: Mapping[str, Any]) -> str:
        if not isinstance(parameters, Mapping):
            raise TypeError("function tool parameters must be a mapping.")
        bound = self._signature.bind(**dict(parameters))
        bound.apply_defaults()
        return str(self.func(*bound.args, **bound.kwargs))

    def _validate_signature(self) -> None:
        unsupported = {
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        }
        if any(
            parameter.kind in unsupported
            for parameter in self._signature.parameters.values()
        ):
            raise ValueError(
                "function tools do not support positional-only, *args, or **kwargs."
            )

    def _infer_schema(self) -> dict[str, Any]:
        properties: dict[str, Any] = {}
        required: list[str] = []
        for parameter in self._signature.parameters.values():
            annotation = parameter.annotation
            json_type = self._json_type(annotation)
            property_schema: dict[str, Any] = {
                "type": json_type,
                "description": f"Parameter '{parameter.name}'.",
            }
            if json_type == "array":
                property_schema["items"] = {"type": "string"}
            if parameter.default is not inspect.Parameter.empty:
                property_schema["description"] += (
                    f" Default: {parameter.default!r}."
                )
            else:
                required.append(parameter.name)
            properties[parameter.name] = property_schema

        return {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }

    @staticmethod
    def _json_type(annotation: Any) -> str:
        if annotation in (inspect.Parameter.empty, Any):
            return "string"
        origin = get_origin(annotation)
        candidate = origin or annotation
        json_type = JSON_TYPES.get(candidate)
        if json_type is None:
            raise ValueError(f"unsupported function parameter annotation: {annotation!r}.")
        return json_type

    @staticmethod
    def _validate_schema(parameters: dict[str, Any]) -> dict[str, Any]:
        schema = deepcopy(parameters)
        if schema.get("type") != "object" or not isinstance(
            schema.get("properties"), dict
        ):
            raise ValueError("function tool parameters must be an object JSON schema.")
        required = schema.get("required", [])
        if not isinstance(required, list) or any(
            not isinstance(name, str) for name in required
        ):
            raise ValueError("function tool required parameters must be a string list.")
        schema.setdefault("additionalProperties", False)
        return schema


__all__ = ["FunctionTool"]
