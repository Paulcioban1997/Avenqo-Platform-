from backend.app.ai.llm.anthropic_provider import AnthropicProvider
from backend.app.ai.llm.base import LLMProvider
from backend.app.ai.llm.exceptions import UnsupportedLLMProviderError
from backend.app.ai.llm.gemini_provider import GeminiProvider
from backend.app.ai.llm.openai_provider import OpenAIProvider
from backend.app.config.settings import Settings


class LLMProviderFactory:
    @staticmethod
    def create(settings: Settings) -> LLMProvider:
        providers = {
            "openai": lambda: OpenAIProvider(settings.openai_api_key, settings.llm_model, settings.llm_temperature, settings.llm_max_tokens),
            "anthropic": lambda: AnthropicProvider(settings.anthropic_api_key, settings.llm_model, settings.llm_temperature, settings.llm_max_tokens),
            "gemini": lambda: GeminiProvider(settings.google_ai_api_key, settings.llm_model, settings.llm_temperature, settings.llm_max_tokens),
        }
        try:
            return providers[settings.llm_provider.lower()]()
        except KeyError as exc:
            raise UnsupportedLLMProviderError("Fournisseur IA non pris en charge") from exc