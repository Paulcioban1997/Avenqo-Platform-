from backend.app.ai.llm.anthropic_provider import AnthropicProvider
from backend.app.ai.llm.base import LLMProvider
from backend.app.ai.llm.circuit_breaker import get_circuit_breaker
from backend.app.ai.llm.exceptions import UnsupportedLLMProviderError
from backend.app.ai.llm.gateway import AvenqoAIGateway
from backend.app.ai.llm.gemini_provider import GeminiProvider
from backend.app.ai.llm.health import get_provider_health_registry
from backend.app.ai.llm.openai_provider import OpenAIProvider
from backend.app.config.settings import Settings


class LLMProviderFactory:
    _BUILDERS = {
        "openai": lambda settings: OpenAIProvider(settings.openai_api_key, settings.openai_model, settings.llm_temperature, settings.llm_max_tokens),
        "anthropic": lambda settings: AnthropicProvider(settings.anthropic_api_key, settings.anthropic_model, settings.llm_temperature, settings.llm_max_tokens),
        "gemini": lambda settings: GeminiProvider(settings.google_ai_api_key, settings.gemini_model, settings.llm_temperature, settings.llm_max_tokens),
    }

    @staticmethod
    def create(settings: Settings) -> LLMProvider:
        """Fournisseur unique (Phase 28) — inchangé, conservé pour compatibilité."""

        try:
            return LLMProviderFactory._BUILDERS[settings.llm_provider.lower()](settings)
        except KeyError as exc:
            raise UnsupportedLLMProviderError("Fournisseur IA non pris en charge") from exc

    @staticmethod
    def _credential_for(settings: Settings, provider_code: str) -> str | None:
        return {
            "openai": settings.openai_api_key,
            "anthropic": settings.anthropic_api_key,
            "gemini": settings.google_ai_api_key,
        }.get(provider_code)

    @staticmethod
    def create_gateway(settings: Settings) -> LLMProvider:
        """Phase 32 : construit le Resilient AI Gateway (primaire + fallbacks).

        Les fallbacks non configurés (pas de clé API) sont ignorés
        silencieusement — jamais de crash de l'application pour un fallback
        optionnel absent. Le primaire est toujours inclus (une mauvaise
        configuration du primaire doit rester visible, pas masquée).
        """

        order = [settings.ai_primary_provider, settings.ai_fallback_provider_1, settings.ai_fallback_provider_2]
        seen: set[str] = set()
        providers: list[LLMProvider] = []
        for index, code in enumerate(order):
            if not code:
                continue
            code = code.lower()
            if code in seen or code not in LLMProviderFactory._BUILDERS:
                continue
            if index > 0 and not LLMProviderFactory._credential_for(settings, code):
                continue
            seen.add(code)
            providers.append(LLMProviderFactory._BUILDERS[code](settings))

        if not providers and settings.ai_primary_provider.lower() in LLMProviderFactory._BUILDERS:
            providers = [LLMProviderFactory._BUILDERS[settings.ai_primary_provider.lower()](settings)]

        breaker = get_circuit_breaker()
        breaker.configure(settings.ai_gateway_circuit_failure_threshold, settings.ai_gateway_circuit_cooldown_seconds)
        return AvenqoAIGateway(
            providers,
            circuit_breaker=breaker,
            health_registry=get_provider_health_registry(),
            max_retries_per_provider=settings.ai_gateway_max_retries,
            base_delay_seconds=settings.ai_gateway_base_delay_seconds,
            max_delay_seconds=settings.ai_gateway_max_delay_seconds,
        )