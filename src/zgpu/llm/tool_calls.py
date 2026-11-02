"""Bounded zGPU tool definitions and execution for remote chat models."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any


class ToolCallError(ValueError):
    """Invalid or unsafe model-requested tool call."""


class ZGPUToolRegistry:
    """Expose a fixed set of typed functions to OpenAI-compatible models."""

    MAX_ARGUMENT_BYTES = 16_384
    MAX_RESULT_CHARS = 16_384

    def __init__(self) -> None:
        self._tools: dict[str, dict[str, Any]] = {}
        self._functions: dict[str, Callable[..., Any]] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        function: Callable[..., Any],
    ) -> None:
        if not name.isascii() or not name.replace("_", "").isalnum() or name in self._tools:
            raise ValueError("tool names must be unique ASCII identifiers")
        self._tools[name] = {
            "type": "function",
            "function": {"name": name, "description": description, "parameters": parameters, "strict": True},
        }
        self._functions[name] = function

    def definitions(self) -> list[dict[str, Any]]:
        return list(self._tools.values())

    def execute(self, name: str, raw_arguments: str) -> str:
        function = self._functions.get(name)
        if function is None:
            raise ToolCallError("unknown zGPU tool")
        if not isinstance(raw_arguments, str):
            raise ToolCallError("tool arguments exceed the size limit")

        def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ToolCallError("tool arguments contain duplicate keys")
                result[key] = value
            return result

        try:
            if len(raw_arguments.encode("utf-8")) > self.MAX_ARGUMENT_BYTES:
                raise ToolCallError("tool arguments exceed the size limit")
            arguments = json.loads(raw_arguments, object_pairs_hook=reject_duplicate_keys)
        except (UnicodeEncodeError, json.JSONDecodeError) as exc:
            raise ToolCallError("tool arguments must be valid JSON") from exc
        if not isinstance(arguments, dict):
            raise ToolCallError("tool arguments must be a JSON object")
        schema = self._tools[name]["function"]["parameters"]
        properties = schema["properties"]
        required = schema.get("required", [])
        if set(arguments) - set(properties) or set(required) - set(arguments):
            raise ToolCallError("tool arguments do not match the declared schema")
        for key, value in arguments.items():
            expected = properties[key]["type"]
            valid = (
                isinstance(value, str)
                if expected == "string"
                else (
                    isinstance(value, int) and not isinstance(value, bool)
                    if expected == "integer"
                    else isinstance(value, bool) if expected == "boolean" else False
                )
            )
            if not valid:
                raise ToolCallError(f"tool argument '{key}' has an invalid type")
            limit = properties[key].get("maxLength")
            if limit is not None and len(value) > limit:
                raise ToolCallError(f"tool argument '{key}' exceeds the size limit")
            minimum, maximum = properties[key].get("minimum"), properties[key].get("maximum")
            if isinstance(value, int) and (
                (minimum is not None and value < minimum) or (maximum is not None and value > maximum)
            ):
                raise ToolCallError(f"tool argument '{key}' is outside the allowed range")
        try:
            result = function(**arguments)
            rendered = json.dumps(result, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        except Exception as exc:
            rendered = json.dumps({"error": str(exc)[:500]}, ensure_ascii=False)
        return rendered[: self.MAX_RESULT_CHARS]
