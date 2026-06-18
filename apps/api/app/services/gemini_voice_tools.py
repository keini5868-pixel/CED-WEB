"""Tools de voz CED — formato Gemini FunctionDeclaration."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from google.genai import types

from app.services.openai_voice_tools import OPENAI_REALTIME_TOOLS

_TYPE_MAP = {
    "string": types.Type.STRING,
    "integer": types.Type.INTEGER,
    "number": types.Type.NUMBER,
    "boolean": types.Type.BOOLEAN,
    "object": types.Type.OBJECT,
    "array": types.Type.ARRAY,
}


def _openai_schema_to_gemini(schema: dict[str, Any]) -> types.Schema:
    raw_type = str(schema.get("type") or "string").lower()
    gemini_type = _TYPE_MAP.get(raw_type, types.Type.STRING)

    props: dict[str, types.Schema] | None = None
    if schema.get("properties"):
        props = {
            str(key): _openai_schema_to_gemini(val if isinstance(val, dict) else {"type": "string"})
            for key, val in schema["properties"].items()
        }

    items = schema.get("items")
    items_schema = _openai_schema_to_gemini(items) if isinstance(items, dict) else None

    return types.Schema(
        type=gemini_type,
        description=schema.get("description"),
        properties=props,
        required=list(schema.get("required") or []) or None,
        enum=list(schema.get("enum") or []) or None,
        items=items_schema,
    )


def openai_tool_to_gemini_declaration(tool: dict[str, Any]) -> types.FunctionDeclaration:
    params = tool.get("parameters") or {"type": "object", "properties": {}}
    return types.FunctionDeclaration(
        name=str(tool.get("name") or ""),
        description=str(tool.get("description") or tool.get("name") or ""),
        parameters=_openai_schema_to_gemini(params),
    )


@lru_cache
def build_gemini_voice_tools() -> types.Tool:
    declarations = [
        openai_tool_to_gemini_declaration(tool)
        for tool in OPENAI_REALTIME_TOOLS
        if tool.get("name")
    ]
    return types.Tool(function_declarations=declarations)
