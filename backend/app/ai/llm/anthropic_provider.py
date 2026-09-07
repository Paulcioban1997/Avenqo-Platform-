from __future__ import annotations

from collections.abc import AsyncIterator

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


def _normalize_anthropic_usage(response, fallback_model: str, *, tool_calls: int = 0) -> LLMUsage:
    raw = getattr(response, "usage", None)
    cached_tokens = int(getattr(raw, "cache_read_input_tokens", 0) or 0)
    cached_tokens += int(getattr(raw, "cache_creation_input_tokens", 0) or 0)
    uncached_tokens = int(getattr(raw, "input_tokens", 0) or 0)
    return LLMUsage(
        provider="anthropic",
        model=getattr(response, "model", None) or fallback_model,
        input_tokens=uncached_tokens + cached_tokens,
        cached_input_tokens=cached_tokens,
        output_tokens=int(getattr(raw, "output_tokens", 0) or 0),
        tool_calls=max(tool_calls, 0),
        provider_request_id=getattr(response, "id", None),
    )


def _anthropic_error_usage(exc: Exception, fallback_model: str) -> LLMUsage | None:
    response = getattr(exc, "response", None)
    source = response if getattr(response, "usage", None) is not None else exc
    if getattr(source, "usage", None) is None:
        return None
    return _normalize_anthropic_usage(source, fallback_model)


class AnthropicProvider(LLMProvider):
    name = "anthropic"
    supports_tool_calling = True

    def __init__(self, api_key: str | None, model: str, temperature: float, max_tokens: int) -> None:
        self._api_key, self._model = api_key, model
        self._temperature, self._max_tokens = temperature, max_tokens

    def _client(self):
        if not self._api_key:
            raise LLMProviderError("Le fournisseur IA n'est pas configuré")
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:
            raise LLMProviderError("La dépendance Anthropic n'est pas installée") from exc
        return AsyncAnthropic(api_key=self._api_key)

    async def generate(self, *, system_instruction: str, prompt: str) -> LLMGeneration:
        try:
            response = await self._client().messages.create(model=self._model, max_tokens=self._max_tokens,
                temperature=self._temperature, system=system_instruction, messages=[{"role": "user", "content": prompt}])
            usage = _normalize_anthropic_usage(response, self._model)
            return LLMGeneration(
                response.content[0].text,
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
                usage=_anthropic_error_usage(exc, self._model),
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
            async with self._client().messages.stream(model=self._model, max_tokens=self._max_tokens,
                temperature=self._temperature, system=system_instruction, messages=[{"role": "user", "content": prompt}]) as stream:
                async for text in stream.text_stream:
                    yield LLMStreamChunk(content=text)
                response = await stream.get_final_message()
                final_usage = _normalize_anthropic_usage(response, self._model)
                yield LLMStreamChunk(usage=final_usage)
        except LLMProviderError:
            raise
        except Exception as exc:
            raise LLMProviderError(
                "Le fournisseur IA est temporairement indisponible",
                usage=final_usage or _anthropic_error_usage(exc, self._model),
            ) from exc

    async def generate_with_tools(
        self,
        *,
        system_instruction: str,
        messages: list[LLMMessage],
        tools: list[ToolDefinition],
    ) -> LLMToolResponse:
        anthropic_messages: list[dict] = []
        for message in messages:
            if message.role == "tool":
                anthropic_messages.append({
                    "role": "user",
                    "content": [{"type": "tool_result", "tool_use_id": message.tool_call_id, "content": message.content}],
                })
            elif message.role == "assistant" and message.tool_calls:
                blocks: list[dict] = []
                if message.content:
                    blocks.append({"type": "text", "text": message.content})
                blocks.extend(
                    {"type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments}
                    for call in message.tool_calls
                )
                anthropic_messages.append({"role": "assistant", "content": blocks})
            else:
                anthropic_messages.append({"role": message.role, "content": message.content})

        anthropic_tools = [
            {"name": tool.name, "description": tool.description, "input_schema": tool.parameters_schema}
            for tool in tools
        ]

        try:
            response = await self._client().messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
                system=system_instruction,
                messages=anthropic_messages,
                tools=anthropic_tools or None,
            )
            text_blocks = [block.text for block in response.content if getattr(block, "type", None) == "text"]
            tool_calls = tuple(
                ToolCall(id=block.id, name=block.name, arguments=block.input)
                for block in response.content
                if getattr(block, "type", None) == "tool_use"
            )
            usage = _normalize_anthropic_usage(response, self._model, tool_calls=len(tool_calls))
            return LLMToolResponse(
                content="".join(text_blocks) or None,
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
                usage=_anthropic_error_usage(exc, self._model),
            ) from exc