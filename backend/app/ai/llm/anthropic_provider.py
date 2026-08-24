from __future__ import annotations

from collections.abc import AsyncIterator

from backend.app.ai.llm.base import LLMProvider
from backend.app.ai.llm.exceptions import LLMProviderError
from backend.app.ai.llm.schemas import LLMGeneration, LLMMessage, LLMToolResponse, ToolDefinition
from backend.app.ai.tools.contracts import ToolCall


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
            return LLMGeneration(response.content[0].text, self.name, self._model,
                {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens})
        except LLMProviderError:
            raise
        except Exception as exc:
            raise LLMProviderError("Le fournisseur IA est temporairement indisponible") from exc

    async def stream(self, *, system_instruction: str, prompt: str) -> AsyncIterator[str]:
        try:
            async with self._client().messages.stream(model=self._model, max_tokens=self._max_tokens,
                temperature=self._temperature, system=system_instruction, messages=[{"role": "user", "content": prompt}]) as stream:
                async for text in stream.text_stream:
                    yield text
        except LLMProviderError:
            raise
        except Exception as exc:
            raise LLMProviderError("Le fournisseur IA est temporairement indisponible") from exc

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
            return LLMToolResponse(
                content="".join(text_blocks) or None,
                tool_calls=tool_calls,
                provider=self.name,
                model=self._model,
                token_usage={"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens},
            )
        except LLMProviderError:
            raise
        except Exception as exc:
            raise LLMProviderError("Le fournisseur IA est temporairement indisponible") from exc