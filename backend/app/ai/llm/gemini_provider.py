from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from backend.app.ai.llm.base import LLMProvider
from backend.app.ai.llm.exceptions import LLMProviderError
from backend.app.ai.llm.schemas import (
    LLMGeneration,
    LLMMessage,
    LLMStreamChunk,
    LLMToolResponse,
    LLMUsage,
    ToolDefinition,
)
from backend.app.ai.tools.contracts import ToolCall

# Champs JSON Schema générés par Pydantic (`model_json_schema()`) mais non
# supportés par le sous-ensemble OpenAPI attendu par l'API Gemini pour les
# `FunctionDeclaration.parameters` (l'API renvoie 400 INVALID_ARGUMENT sinon).
_GEMINI_UNSUPPORTED_SCHEMA_KEYS = frozenset({
    "additionalProperties",
    "title",
    "$schema",
    "$defs",
    "definitions",
    "default",
    "examples",
    "example",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "discriminator",
    "prefixItems",
    "minItems",
    "maxItems",
    "uniqueItems",
    "patternProperties",
    "propertyNames",
    "unevaluatedProperties",
    "const",
})
_GEMINI_SUPPORTED_FORMATS = frozenset({"enum", "date-time"})
_GEMINI_TYPE_PRECEDENCE = ("object", "array", "string", "number", "integer", "boolean")


def _sanitize_schema_for_gemini(
    schema: Any,
    *,
    defs: dict[str, Any] | None = None,
    seen_refs: frozenset[str] = frozenset(),
) -> Any:
    """Convertit un JSON Schema Pydantic v2 en sous-ensemble OpenAPI strict Gemini."""
    if isinstance(schema, list):
        return [_sanitize_schema_for_gemini(item, defs=defs, seen_refs=seen_refs) for item in schema]
    if not isinstance(schema, dict):
        return schema

    active_defs = defs
    if active_defs is None:
        raw_defs = schema.get("$defs") or schema.get("definitions")
        active_defs = raw_defs if isinstance(raw_defs, dict) else {}

    # Résolution des références $ref (#/$defs/... ou #/definitions/...)
    if isinstance(schema.get("$ref"), str):
        ref_str = schema["$ref"]
        ref_name = ref_str.rsplit("/", 1)[-1]
        if ref_name in active_defs and ref_name not in seen_refs:
            resolved = dict(active_defs[ref_name])
            if "description" in schema and "description" not in resolved:
                resolved["description"] = schema["description"]
            return _sanitize_schema_for_gemini(
                resolved,
                defs=active_defs,
                seen_refs=seen_refs | {ref_name},
            )
        return {"type": "string", "description": str(schema.get("description") or "")}

    # Gestion anyOf / oneOf (Pydantic v2 Optional[T] => anyOf: [{type: T}, {type: null}])
    for union_key in ("anyOf", "oneOf"):
        variants = schema.get(union_key)
        if isinstance(variants, list) and variants:
            sanitized_variants = [
                _sanitize_schema_for_gemini(v, defs=active_defs, seen_refs=seen_refs)
                for v in variants
            ]
            has_null = any(isinstance(v, dict) and v.get("type") == "null" for v in sanitized_variants)
            non_null = [v for v in sanitized_variants if isinstance(v, dict) and v.get("type") != "null"]
            if not non_null:
                chosen: dict[str, Any] = {"type": "string"}
            elif len(non_null) == 1:
                chosen = dict(non_null[0])
            else:
                def _rank(branch: dict[str, Any]) -> int:
                    btype = str(branch.get("type") or "")
                    return _GEMINI_TYPE_PRECEDENCE.index(btype) if btype in _GEMINI_TYPE_PRECEDENCE else len(_GEMINI_TYPE_PRECEDENCE)
                chosen = dict(min(non_null, key=_rank))
            if has_null:
                chosen["nullable"] = True
            if "description" in schema and "description" not in chosen:
                chosen["description"] = schema["description"]
            return chosen

    result: dict[str, Any] = {}
    if "const" in schema:
        const_val = schema["const"]
        result["enum"] = [const_val]
        if "type" not in schema:
            if isinstance(const_val, bool):
                result["type"] = "boolean"
            elif isinstance(const_val, int):
                result["type"] = "integer"
            elif isinstance(const_val, float):
                result["type"] = "number"
            else:
                result["type"] = "string"

    for key, value in schema.items():
        if key in _GEMINI_UNSUPPORTED_SCHEMA_KEYS or key in ("$ref", "anyOf", "oneOf"):
            continue
        if key == "format":
            if isinstance(value, str) and value in _GEMINI_SUPPORTED_FORMATS:
                result["format"] = value
            continue
        if key == "type":
            if isinstance(value, list):
                non_null_types = [t for t in value if t != "null"]
                if "null" in value:
                    result["nullable"] = True
                result["type"] = non_null_types[0] if non_null_types else "string"
            elif value == "null":
                result["type"] = "string"
                result["nullable"] = True
            else:
                result["type"] = value
            continue
        if key == "properties" and isinstance(value, dict):
            result["properties"] = {
                prop_name: _sanitize_schema_for_gemini(prop_schema, defs=active_defs, seen_refs=seen_refs)
                for prop_name, prop_schema in value.items()
            }
            continue
        result[key] = _sanitize_schema_for_gemini(value, defs=active_defs, seen_refs=seen_refs)

    if isinstance(result.get("properties"), dict) and isinstance(result.get("required"), list):
        valid_props = set(result["properties"].keys())
        filtered_req = [item for item in result["required"] if item in valid_props]
        if filtered_req:
            result["required"] = filtered_req
        else:
            result.pop("required", None)

    if defs is None and result.get("type") in (None, "object") and "properties" not in result:
        result["type"] = "object"
        result["properties"] = {}

    return result


def _normalize_gemini_usage(response, fallback_model: str, *, tool_calls: int = 0, provider: str = "gemini") -> LLMUsage:
    raw = getattr(response, "usage_metadata", None)
    if raw is None or getattr(raw, "prompt_token_count", None) is None:
        raise LLMProviderError("Provider usage metadata unavailable")
    return LLMUsage(
        provider=provider,
        model=getattr(response, "model_version", None) or fallback_model,
        input_tokens=int(getattr(raw, "prompt_token_count", 0) or 0),
        cached_input_tokens=int(getattr(raw, "cached_content_token_count", 0) or 0),
        output_tokens=int(getattr(raw, "candidates_token_count", 0) or 0) + int(getattr(raw, "thoughts_token_count", 0) or 0),
        reasoning_tokens=int(getattr(raw, "thoughts_token_count", 0) or 0),
        tool_calls=max(tool_calls, 0),
        provider_request_id=getattr(response, "response_id", None),
    )


def _gemini_error_usage(exc: Exception, fallback_model: str, *, provider: str = "gemini") -> LLMUsage | None:
    response = getattr(exc, "response", None)
    source = response if getattr(response, "usage_metadata", None) is not None else exc
    if getattr(source, "usage_metadata", None) is None:
        return None
    return _normalize_gemini_usage(source, fallback_model, provider=provider)


class GeminiProvider(LLMProvider):
    name = "gemini"
    supports_tool_calling = True

    def __init__(
        self,
        api_key: str | None,
        model: str,
        temperature: float,
        max_tokens: int,
        request_timeout_seconds: float = 60.0,
    ) -> None:
        self._api_key, self._model = api_key, model
        self._temperature, self._max_tokens = temperature, max_tokens
        self._request_timeout_seconds = request_timeout_seconds
        self._client_instance = None

    def _client(self):
        if not self._api_key:
            raise LLMProviderError("Le fournisseur IA n'est pas configuré")
        if self._client_instance is not None:
            return self._client_instance
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise LLMProviderError("La dépendance Google GenAI n'est pas installée") from exc
        self._client_instance = genai.Client(
            enterprise=False,
            vertexai=False,
            api_key=self._api_key,
            http_options=types.HttpOptions(
                timeout=max(1, int(self._request_timeout_seconds * 1000)),
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )
        return self._client_instance

    async def _async_client(self):
        return await asyncio.to_thread(self._client)

    async def generate(self, *, system_instruction: str, prompt: str) -> LLMGeneration:
        try:
            from google.genai import types
            client = await self._async_client()
            response = await client.aio.models.generate_content(model=self._model, contents=prompt,
                config=types.GenerateContentConfig(system_instruction=system_instruction, temperature=self._temperature,
                max_output_tokens=self._max_tokens))
            usage = _normalize_gemini_usage(response, self._model, provider=self.name)
            return LLMGeneration(
                response.text or "",
                self.name,
                usage.model,
                usage.as_token_usage(),
                usage=usage,
            )
        except LLMProviderError:
            raise
        except Exception as exc:
            raise LLMProviderError(
                "Le fournisseur IA est temporairement indisponible",
                usage=_gemini_error_usage(exc, self._model, provider=self.name),
            ) from exc

    async def stream(self, *, system_instruction: str, prompt: str) -> AsyncIterator[str]:
        async for event in self.stream_events(system_instruction=system_instruction, prompt=prompt):
            if event.content:
                yield event.content

    async def stream_events(
        self,
        *,
        system_instruction: str,
        prompt: str,
    ) -> AsyncIterator[LLMStreamChunk]:
        final_response = None
        try:
            from google.genai import types
            client = await self._async_client()
            stream = await client.aio.models.generate_content_stream(model=self._model, contents=prompt,
                config=types.GenerateContentConfig(system_instruction=system_instruction, temperature=self._temperature,
                max_output_tokens=self._max_tokens))
            async for event in stream:
                if getattr(event, "usage_metadata", None) is not None:
                    final_response = event
                if event.text:
                    yield LLMStreamChunk(content=event.text)
            yield LLMStreamChunk(usage=_normalize_gemini_usage(final_response, self._model, provider=self.name))
        except LLMProviderError:
            raise
        except Exception as exc:
            usage = (
                _normalize_gemini_usage(final_response, self._model, provider=self.name)
                if final_response is not None and getattr(final_response, "usage_metadata", None) is not None
                else _gemini_error_usage(exc, self._model, provider=self.name)
            )
            raise LLMProviderError(
                "Le fournisseur IA est temporairement indisponible",
                usage=usage,
            ) from exc

    async def generate_with_tools(
        self,
        *,
        system_instruction: str,
        messages: list[LLMMessage],
        tools: list[ToolDefinition],
    ) -> LLMToolResponse:
        try:
            from google.genai import types

            contents: list[types.Content] = []
            for message in messages:
                if message.role == "tool":
                    try:
                        raw_content = message.content or ""
                        parsed_resp = json.loads(raw_content) if isinstance(raw_content, str) else raw_content
                        resp_dict = parsed_resp if isinstance(parsed_resp, dict) else {"result": parsed_resp}
                    except Exception:
                        resp_dict = {"result": message.content}
                    part = types.Part.from_function_response(
                        name=message.name or "",
                        response=resp_dict,
                    )
                    # GenAI strictly requires all consecutive function responses following a model turn
                    # to be grouped into a single types.Content(role="user", parts=[...])
                    if contents and contents[-1].role == "user" and any(
                        getattr(p, "function_response", None) is not None for p in contents[-1].parts
                    ):
                        contents[-1].parts.append(part)
                    else:
                        contents.append(types.Content(role="user", parts=[part]))
                elif message.role == "assistant" and message.tool_calls:
                    parts = []
                    if message.content:
                        parts.append(types.Part(text=message.content))
                    for call in message.tool_calls:
                        call_part = types.Part.from_function_call(name=call.name, args=call.arguments)
                        if call.provider_metadata:
                            call_part.thought_signature = call.provider_metadata
                        parts.append(call_part)
                    contents.append(types.Content(role="model", parts=parts))
                else:
                    role = "model" if message.role == "assistant" else "user"
                    contents.append(types.Content(role=role, parts=[types.Part(text=message.content)]))

            declarations = [
                types.FunctionDeclaration(
                    name=tool.name,
                    description=tool.description,
                    parameters=_sanitize_schema_for_gemini(tool.parameters_schema),
                )
                for tool in tools
            ]
            config = types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=self._temperature,
                max_output_tokens=self._max_tokens,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                tools=[types.Tool(function_declarations=declarations)] if declarations else None,
            )
            client = await self._async_client()
            response = await client.aio.models.generate_content(model=self._model, contents=contents, config=config)

            tool_calls: list[ToolCall] = []
            text_parts: list[str] = []
            candidate = response.candidates[0] if response.candidates else None
            for part in (candidate.content.parts if candidate else []):
                if getattr(part, "function_call", None) is not None:
                    call = part.function_call
                    tool_calls.append(ToolCall(
                        id=call.name, name=call.name, arguments=dict(call.args or {}),
                        provider_metadata=getattr(part, "thought_signature", None),
                    ))
                elif getattr(part, "text", None):
                    text_parts.append(part.text)

            usage = _normalize_gemini_usage(response, self._model, tool_calls=len(tool_calls), provider=self.name)
            return LLMToolResponse(
                content="".join(text_parts) or None,
                tool_calls=tuple(tool_calls),
                provider=self.name,
                model=usage.model,
                token_usage=usage.as_token_usage(),
                usage=usage,
            )
        except LLMProviderError:
            raise
        except Exception as exc:
            raise LLMProviderError(
                "Le fournisseur IA est temporairement indisponible",
                usage=_gemini_error_usage(exc, self._model, provider=self.name),
            ) from exc