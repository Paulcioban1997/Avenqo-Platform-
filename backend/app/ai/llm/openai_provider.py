from __future__ import annotations

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


def _normalize_openai_usage(response, fallback_model: str, *, tool_calls: int = 0) -> LLMUsage:
    usage = getattr(response, "usage", None)
    prompt_details = getattr(usage, "prompt_tokens_details", None)
    completion_details = getattr(usage, "completion_tokens_details", None)
    input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    return LLMUsage(
        provider="openai",
        model=getattr(response, "model", None) or fallback_model,
        input_tokens=input_tokens,
        cached_input_tokens=min(
            int(getattr(prompt_details, "cached_tokens", 0) or 0),
            input_tokens,
        ),
        output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
        reasoning_tokens=int(getattr(completion_details, "reasoning_tokens", 0) or 0),
        tool_calls=max(tool_calls, 0),
        provider_request_id=getattr(response, "id", None),
    )


def _openai_error_usage(exc: Exception, fallback_model: str) -> LLMUsage | None:
    response = getattr(exc, "response", None)
    source = response if getattr(response, "usage", None) is not None else exc
    if getattr(source, "usage", None) is None:
        return None
    return _normalize_openai_usage(source, fallback_model)


def _is_reasoning_chat_model(model: str | None) -> bool:
    """Return True for OpenAI reasoning models requiring max_completion_tokens + reasoning_effort."""
    low = (model or "").strip().lower()
    return any(tok in low for tok in ("gpt-6.2", "gpt-6-1-sol", "-sol", "-astra", "o1", "o3", "o4", "reasoning"))


def _build_completion_params(
    model: str | None,
    *,
    temperature: float,
    max_tokens: int,
    reasoning_effort: str | None = None,
) -> dict[str, Any]:
    """Build Chat Completions kwargs compatible with GPT-6.2 Sol/Astra and legacy GPT-4o models.

    OpenAI GPT-6.2 Sol/Astra reject legacy `max_tokens`, reject custom `temperature` when
    reasoning is enabled, and reject `reasoning_effort='none'` (minimum valid is `'low'`).
    """
    if _is_reasoning_chat_model(model):
        low = (model or "").strip().lower()
        default_effort = "low" if "sol" in low else "medium"
        effort = (reasoning_effort or default_effort).strip().lower()
        if effort not in {"low", "medium", "high", "xhigh", "max"}:
            effort = default_effort
        return {
            "max_completion_tokens": max_tokens,
            "reasoning_effort": effort,
        }
    return {
        "temperature": temperature,
        "max_tokens": max_tokens,
    }


class OpenAIProvider(LLMProvider):
    name = "openai"
    supports_tool_calling = True

    def __init__(
        self,
        api_key: str | None,
        model: str,
        temperature: float,
        max_tokens: int,
        request_timeout_seconds: float = 60.0,
        *,
        reasoning_effort: str | None = None,
    ) -> None:
        self._api_key, self._model = api_key, model
        self._temperature, self._max_tokens = temperature, max_tokens
        self._request_timeout_seconds = request_timeout_seconds
        self._reasoning_effort = reasoning_effort

    def _client(self):
        if not self._api_key:
            raise LLMProviderError("Le fournisseur IA n'est pas configuré")
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise LLMProviderError("La dépendance OpenAI n'est pas installée") from exc
        return AsyncOpenAI(api_key=self._api_key, timeout=self._request_timeout_seconds, max_retries=0)

    async def generate(self, *, system_instruction: str, prompt: str) -> LLMGeneration:
        try:
            req_kwargs: dict[str, Any] = {
                "model": self._model,
                "messages": [{"role": "system", "content": system_instruction}, {"role": "user", "content": prompt}],
                **_build_completion_params(
                    self._model,
                    temperature=self._temperature,
                    max_tokens=self._max_tokens,
                    reasoning_effort=self._reasoning_effort,
                ),
            }

            response = await self._client().chat.completions.create(**req_kwargs)
            usage = _normalize_openai_usage(response, self._model)
            return LLMGeneration(
                response.choices[0].message.content or "",
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
                usage=_openai_error_usage(exc, self._model),
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
        final_usage = None
        try:
            stream = await self._client().chat.completions.create(
                model=self._model,
                stream=True,
                stream_options={"include_usage": True},
                messages=[{"role": "system", "content": system_instruction}, {"role": "user", "content": prompt}],
                **_build_completion_params(
                    self._model,
                    temperature=self._temperature,
                    max_tokens=self._max_tokens,
                    reasoning_effort=self._reasoning_effort,
                ),
            )
            async for event in stream:
                content = event.choices[0].delta.content if event.choices else None
                if content:
                    yield LLMStreamChunk(content=content)
                if getattr(event, "usage", None) is not None:
                    final_usage = _normalize_openai_usage(event, self._model)
                    yield LLMStreamChunk(usage=final_usage)
        except LLMProviderError:
            raise
        except Exception as exc:
            raise LLMProviderError(
                "Le fournisseur IA est temporairement indisponible",
                usage=final_usage or _openai_error_usage(exc, self._model),
            ) from exc

    async def generate_with_tools(
        self,
        *,
        system_instruction: str,
        messages: list[LLMMessage],
        tools: list[ToolDefinition],
    ) -> LLMToolResponse:
        openai_messages: list[dict[str, Any]] = [{"role": "system", "content": system_instruction}]
        for message in messages:
            if message.role == "tool":
                openai_messages.append(
                    {"role": "tool", "tool_call_id": message.tool_call_id, "content": message.content}
                )
            elif message.role == "assistant" and message.tool_calls:
                openai_messages.append({
                    "role": "assistant",
                    "content": message.content or None,
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
                        }
                        for call in message.tool_calls
                    ],
                })
            else:
                openai_messages.append({"role": message.role, "content": message.content})

        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters_schema,
                },
            }
            for tool in tools
        ]

        try:
            req_kwargs: dict[str, Any] = {
                "model": self._model,
                "messages": openai_messages,
                "tools": openai_tools or None,
                **_build_completion_params(
                    self._model,
                    temperature=self._temperature,
                    max_tokens=self._max_tokens,
                    reasoning_effort=self._reasoning_effort,
                ),
            }

            response = await self._client().chat.completions.create(**req_kwargs)
            choice = response.choices[0].message
            tool_calls = tuple(
                ToolCall(id=call.id, name=call.function.name, arguments=json.loads(call.function.arguments or "{}"))
                for call in (choice.tool_calls or [])
            )
            usage = _normalize_openai_usage(response, self._model, tool_calls=len(tool_calls))
            return LLMToolResponse(
                content=choice.content,
                tool_calls=tool_calls,
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
                usage=_openai_error_usage(exc, self._model),
            ) from exc