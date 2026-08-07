"""Native Chat Completions function-calling agent."""

import json
import re
from copy import deepcopy
from typing import Any, Literal, TypedDict

from ..core.agent import Agent
from ..core.config import Config
from ..core.llm import HelloAgentsLLM
from ..core.message import Message
from ..tools import ToolRegistry


TOOL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MAX_FUNCTION_ITERATIONS = 10
MAX_TOOL_CALLS_PER_RESPONSE = 4
ToolCallStatus = Literal["completed", "failed"]


class ToolCallRecord(TypedDict):
    name: str
    arguments: dict[str, Any]
    result: str
    status: ToolCallStatus


class FunctionCallAgent(Agent):
    """Execute provider-native structured tool calls within a bounded loop."""

    def __init__(
        self,
        name: str,
        llm: HelloAgentsLLM,
        tool_registry: ToolRegistry,
        system_prompt: str | None = None,
        config: Config | None = None,
        max_iterations: int = 5,
        tool_choice: str | dict[str, Any] = "auto",
    ) -> None:
        super().__init__(name, llm, system_prompt, config)
        if not isinstance(tool_registry, ToolRegistry):
            raise TypeError("tool_registry must be a ToolRegistry instance.")
        if not 1 <= max_iterations <= MAX_FUNCTION_ITERATIONS:
            raise ValueError(
                "max_iterations must be between "
                f"1 and {MAX_FUNCTION_ITERATIONS}."
            )
        if not isinstance(tool_choice, (str, dict)):
            raise TypeError("tool_choice must be a string or dictionary.")

        self.tool_registry = tool_registry
        self.max_iterations = max_iterations
        self.tool_choice = tool_choice
        self.current_tool_calls: list[ToolCallRecord] = []

    def run(self, input_text: str, **kwargs: Any) -> str:
        """Run one native function-calling conversation turn."""
        user_input = input_text.strip()
        if not user_input:
            raise ValueError("input_text must not be empty.")

        messages: list[dict[str, Any]] = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.extend(message.to_dict() for message in self.get_history())
        messages.append({"role": "user", "content": user_input})
        tools = self._build_tool_schemas()
        self.current_tool_calls = []

        for _ in range(self.max_iterations):
            completion = self._invoke_with_tools(
                messages,
                tools,
                self.tool_choice,
                **kwargs,
            )
            response_message = completion.choices[0].message
            content = self._extract_message_content(response_message)
            tool_calls = list(getattr(response_message, "tool_calls", None) or [])

            if not tool_calls:
                answer = content or "抱歉，模型没有返回最终答案。"
                return self._finish(user_input, answer)
            if len(tool_calls) > MAX_TOOL_CALLS_PER_RESPONSE:
                return self._finish(user_input, "抱歉，单轮工具调用数量超过安全上限。")

            messages.append(
                {
                    "role": "assistant",
                    "content": content or None,
                    "tool_calls": [self._serialize_tool_call(call) for call in tool_calls],
                }
            )
            for call in tool_calls:
                call_id = getattr(call, "id", None)
                if not isinstance(call_id, str) or not call_id:
                    raise RuntimeError("model returned a tool call without an id.")
                result = self._execute_tool_call(call)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": result,
                    }
                )

        return self._finish(
            user_input,
            "抱歉，函数调用达到迭代上限，未获得最终答案。",
        )

    def _build_tool_schemas(self) -> list[dict[str, Any]]:
        schemas: list[dict[str, Any]] = []
        for name in self.tool_registry.list_tools():
            tool = self.tool_registry.get_tool(name)
            if tool is None:
                continue
            if not TOOL_NAME_PATTERN.fullmatch(name):
                raise ValueError(f"tool name '{name}' is not valid for function calling.")
            parameters = deepcopy(tool.parameters)
            if parameters.get("type") != "object" or not isinstance(
                parameters.get("properties"), dict
            ):
                raise ValueError(f"tool '{name}' has an invalid parameter schema.")
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": tool.description,
                        "parameters": parameters,
                    },
                }
            )
        return schemas

    @staticmethod
    def _extract_message_content(response_message: Any) -> str:
        content = getattr(response_message, "content", None)
        if content is None:
            return ""
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for part in content:
                text = part.get("text") if isinstance(part, dict) else getattr(part, "text", None)
                if isinstance(text, str):
                    parts.append(text)
            return "".join(parts).strip()
        return str(content).strip()

    @staticmethod
    def _parse_function_call_arguments(arguments: str) -> dict[str, Any]:
        try:
            parsed = json.loads(arguments)
        except (json.JSONDecodeError, TypeError) as error:
            raise ValueError("function arguments must be valid JSON.") from error
        if not isinstance(parsed, dict):
            raise ValueError("function arguments must be a JSON object.")
        return parsed

    def _execute_tool_call(self, call: Any) -> str:
        function = getattr(call, "function", None)
        name = getattr(function, "name", "")
        raw_arguments = getattr(function, "arguments", "")
        arguments: dict[str, Any] = {}
        try:
            tool = self.tool_registry.get_tool(name)
            if tool is None:
                raise KeyError(f"tool '{name}' is not registered.")
            arguments = self._parse_function_call_arguments(raw_arguments)
            arguments = self._convert_parameter_types(arguments, tool.parameters)
            result = self.tool_registry.execute_tool(name, arguments)
            status: ToolCallStatus = "completed"
        except Exception as error:
            result = f"工具调用失败：{type(error).__name__}"
            status = "failed"

        self.current_tool_calls.append(
            {
                "name": str(name),
                "arguments": arguments,
                "result": result,
                "status": status,
            }
        )
        return result

    @classmethod
    def _convert_parameter_types(
        cls,
        arguments: dict[str, Any],
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        missing = [name for name in required if name not in arguments]
        if missing:
            raise ValueError(f"missing required parameters: {', '.join(missing)}.")
        if schema.get("additionalProperties") is False:
            unexpected = set(arguments) - set(properties)
            if unexpected:
                raise ValueError(
                    "unexpected parameters: " + ", ".join(sorted(unexpected)) + "."
                )

        converted: dict[str, Any] = {}
        for name, value in arguments.items():
            parameter_schema = properties.get(name, {})
            converted_value = cls._convert_value(value, parameter_schema.get("type"))
            enum = parameter_schema.get("enum")
            if enum is not None and converted_value not in enum:
                raise ValueError(f"parameter '{name}' is outside its enum.")
            converted[name] = converted_value
        return converted

    @staticmethod
    def _convert_value(value: Any, expected_type: str | None) -> Any:
        if expected_type in (None, "object", "array"):
            if expected_type == "object" and not isinstance(value, dict):
                raise ValueError("expected an object parameter.")
            if expected_type == "array" and not isinstance(value, list):
                raise ValueError("expected an array parameter.")
            return value
        if expected_type == "string":
            if isinstance(value, (dict, list)):
                raise ValueError("expected a string parameter.")
            return str(value)
        if expected_type == "integer":
            if isinstance(value, bool):
                raise ValueError("expected an integer parameter.")
            converted = int(value)
            if isinstance(value, float) and not value.is_integer():
                raise ValueError("expected an integer parameter.")
            return converted
        if expected_type == "number":
            if isinstance(value, bool):
                raise ValueError("expected a number parameter.")
            return float(value)
        if expected_type == "boolean":
            if isinstance(value, bool):
                return value
            if isinstance(value, str) and value.lower() in {"true", "false"}:
                return value.lower() == "true"
            raise ValueError("expected a boolean parameter.")
        raise ValueError(f"unsupported JSON schema type '{expected_type}'.")

    @staticmethod
    def _serialize_tool_call(call: Any) -> dict[str, Any]:
        function = getattr(call, "function", None)
        return {
            "id": getattr(call, "id", ""),
            "type": "function",
            "function": {
                "name": getattr(function, "name", ""),
                "arguments": getattr(function, "arguments", ""),
            },
        }

    def _invoke_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: str | dict[str, Any],
        **kwargs: Any,
    ) -> Any:
        client = getattr(self.llm, "_client", None) or getattr(self.llm, "client", None)
        if client is None:
            raise RuntimeError(
                "HelloAgentsLLM is not initialized with a Chat Completions client."
            )
        options = {
            key: value
            for key, value in kwargs.items()
            if key not in {"stream", "tools", "tool_choice"}
        }
        return client.chat.completions.create(
            model=self.llm.model,
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            stream=False,
            **options,
        )

    def _finish(self, user_input: str, answer: str) -> str:
        self.add_message(Message(content=user_input, role="user"))
        self.add_message(Message(content=answer, role="assistant"))
        return answer


__all__ = ["FunctionCallAgent", "ToolCallRecord"]
