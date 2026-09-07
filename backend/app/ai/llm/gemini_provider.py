from __future__ import annotations

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
_GEMINI_UNSUPPORTED_SCHEMA_KEYS = frozenset({"additionalProperties", "title", "$schema", "default"})


def _sanitize_schema_for_gemini(schema: Any) -> Any:
    """Retire récursivement les clés JSON Schema non supportées par Gemini."""

    if isinstance(schema, dict):
        return {
            key: _sanitize_schema_for_gemini(value)
            for key, value in schema.items()
            if key not in _GEMINI_UNSUPPORTED_SCHEMA_KEYS
        }
    if isinstance(schema, list):
        return [_sanitize_schema_for_gemini(item) for item in schema]
    return schema


def _normalize_gemini_usage(response, fallback_model: str, *, tool_calls: int = 0) -> LLMUsage:
    raw = getattr(response, "usage_metadata", None)
    return LLMUsage(
        provider="gemini",
        model=getattr(response, "model_version", None) or fallback_model,
        input_tokens=int(getattr(raw, "prompt_token_count", 0) or 0),
        cached_input_tokens=int(getattr(raw, "cached_content_token_count", 0) or 0),
        output_tokens=int(getattr(raw, "candidates_token_count", 0) or 0),
        reasoning_tokens=int(getattr(raw, "thoughts_token_count", 0) or 0),
        tool_calls=max(tool_calls, 0),
        provider_request_id=getattr(response, "response_id", None),
    )


def _gemini_error_usage(exc: Exception, fallback_model: str) -> LLMUsage | None:
    response = getattr(exc, "response", None)
    source = response if getattr(response, "usage_metadata", None) is not None else exc
    if getattr(source, "usage_metadata", None) is None:
        return None
    return _normalize_gemini_usage(source, fallback_model)


class GeminiProvider(LLMProvider):
    name = "gemini"
    supports_tool_calling = True

    def __init__(self, api_key: str | None, model: str, temperature: float, max_tokens: int) -> None:
        self._api_key, self._model = api_key, model
        self._temperature, self._max_tokens = temperature, max_tokens
        self._client_instance = None

    def _client(self):
        if not self._api_key:
            raise LLMProviderError("Le fournisseur IA n'est pas configuré")
        if self._client_instance is not None:
            return self._client_instance
        try:
            from google import genai
        except ImportError as exc:
            raise LLMProviderError("La dépendance Google GenAI n'est pas installée") from exc
        self._client_instance = genai.Client(api_key=self._api_key)
        return self._client_instance

    async def generate(self, *, system_instruction: str, prompt: str) -> LLMGeneration:
        try:
            from google.genai import types
            response = await self._client().aio.models.generate_content(model=self._model, contents=prompt,
                config=types.GenerateContentConfig(system_instruction=system_instruction, temperature=self._temperature,
                max_output_tokens=self._max_tokens))
            usage = _normalize_gemini_usage(response, self._model)
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
                usage=_gemini_error_usage(exc, self._model),
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
            stream = await self._client().aio.models.generate_content_stream(model=self._model, contents=prompt,
                config=types.GenerateContentConfig(system_instruction=system_instruction, temperature=self._temperature,
                max_output_tokens=self._max_tokens))
            async for event in stream:
                final_response = event
                if event.text:
                    yield LLMStreamChunk(content=event.text)
            if final_response is not None:
                yield LLMStreamChunk(usage=_normalize_gemini_usage(final_response, self._model))
        except LLMProviderError:
            raise
        except Exception as exc:
            usage = (
                _normalize_gemini_usage(final_response, self._model)
                if final_response is not None and getattr(final_response, "usage_metadata", None) is not None
                else _gemini_error_usage(exc, self._model)
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

            contents = []
            for message in messages:
                if message.role == "tool":
                    contents.append(types.Content(role="user", parts=[
                        types.Part.from_function_response(name=message.name or "", response={"result": message.content})
                    ]))
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
                tools=[types.Tool(function_declarations=declarations)] if declarations else None,
            )
            response = await self._client().aio.models.generate_content(model=self._model, contents=contents, config=config)

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

            usage = _normalize_gemini_usage(response, self._model, tool_calls=len(tool_calls))
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
                usage=_gemini_error_usage(exc, self._model),
            ) from exc