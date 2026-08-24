from __future__ import annotations

import json
from collections.abc import AsyncIterator

from backend.app.ai.llm.base import LLMProvider
from backend.app.ai.llm.exceptions import LLMProviderError
from backend.app.ai.llm.schemas import LLMGeneration, LLMMessage, LLMToolResponse, ToolDefinition
from backend.app.ai.tools.contracts import ToolCall


class OpenAIProvider(LLMProvider):
    name = "openai"
    supports_tool_calling = True

    def __init__(self, api_key: str | None, model: str, temperature: float, max_tokens: int) -> None:
        self._api_key, self._model = api_key, model
        self._temperature, self._max_tokens = temperature, max_tokens

    def _client(self):
        if not self._api_key:
            raise LLMProviderError("Le fournisseur IA n'est pas configuré")
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise LLMProviderError("La dépendance OpenAI n'est pas installée") from exc
        return AsyncOpenAI(api_key=self._api_key)

    async def generate(self, *, system_instruction: str, prompt: str) -> LLMGeneration:
        try:
            response = await self._client().chat.completions.create(
                model=self._model, temperature=self._temperature, max_tokens=self._max_tokens,
                messages=[{"role": "system", "content": system_instruction}, {"role": "user", "content": prompt}],
            )
            usage = response.usage
            return LLMGeneration(response.choices[0].message.content or "", self.name, self._model,
                                 {"input_tokens": usage.prompt_tokens, "output_tokens": usage.completion_tokens} if usage else {})
        except LLMProviderError:
            raise
        except Exception as exc:
            raise LLMProviderError("Le fournisseur IA est temporairement indisponible") from exc

    async def stream(self, *, system_instruction: str, prompt: str) -> AsyncIterator[str]:
        try:
            stream = await self._client().chat.completions.create(
                model=self._model, temperature=self._temperature, max_tokens=self._max_tokens, stream=True,
                messages=[{"role": "system", "content": system_instruction}, {"role": "user", "content": prompt}],
            )
            async for event in stream:
                content = event.choices[0].delta.content if event.choices else None
                if content:
                    yield content
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
        openai_messages = [{"role": "system", "content": system_instruction}]
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
            response = await self._client().chat.completions.create(
                model=self._model,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
                messages=openai_messages,
                tools=openai_tools or None,
            )
            choice = response.choices[0].message
            tool_calls = tuple(
                ToolCall(id=call.id, name=call.function.name, arguments=json.loads(call.function.arguments or "{}"))
                for call in (choice.tool_calls or [])
            )
            usage = response.usage
            return LLMToolResponse(
                content=choice.content,
                tool_calls=tool_calls,
                provider=self.name,
                model=self._model,
                token_usage={"input_tokens": usage.prompt_tokens, "output_tokens": usage.completion_tokens} if usage else {},
            )
        except LLMProviderError:
            raise
        except Exception as exc:
            raise LLMProviderError("Le fournisseur IA est temporairement indisponible") from exc