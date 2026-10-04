import logging
import os

from backend.app.ai.llm.anthropic_provider import AnthropicProvider
from backend.app.ai.llm.base import LLMProvider
from backend.app.ai.llm.circuit_breaker import get_circuit_breaker
from backend.app.ai.llm.exceptions import UnsupportedLLMProviderError
from backend.app.ai.llm.gateway import AvenqoAIGateway
from backend.app.ai.llm.gemini_provider import GeminiProvider
from backend.app.ai.llm.health import get_provider_health_registry
from backend.app.ai.llm.model_registry import LLMModelRegistry, LLMModelSpec, LLMRateCard
from backend.app.ai.llm.openai_provider import OpenAIProvider
from backend.app.ai.llm.provider_registry import DEFAULT_LLM_PROVIDER_REGISTRY
from backend.app.ai.llm.router import SmartModelRouter
from backend.app.ai.llm.vertex_provider import VertexProvider
from backend.app.config.settings import Settings

logger = logging.getLogger("avenqo.ai.factory")


class LLMProviderFactory:
    _BUILDERS = {
        "openai": lambda settings: OpenAIProvider(settings.openai_api_key, settings.openai_model, settings.llm_temperature, settings.llm_max_tokens),
        "anthropic": lambda settings: AnthropicProvider(settings.anthropic_api_key, settings.anthropic_model, settings.llm_temperature, settings.llm_max_tokens),
        "gemini": lambda settings: GeminiProvider(settings.google_ai_api_key, settings.gemini_model, settings.llm_temperature, settings.llm_max_tokens),
        "vertex": lambda settings: VertexProvider(
            settings.vertex_project,
            settings.vertex_location,
            settings.vertex_model,
            settings.llm_temperature,
            settings.llm_max_tokens,
            enabled=settings.vertex_enabled,
            service_account_email=settings.vertex_service_account_email,
            service_account_json=settings.google_service_account_json,
        ),
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
        if provider_code.casefold() == "vertex":
            if not settings.vertex_enabled or not all((
                settings.vertex_project.strip(),
                settings.vertex_location.strip(),
                settings.vertex_model.strip(),
            )):
                return None
            if settings.google_service_account_json:
                return "service_account_json"
            if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
                return "adc_file"
            return None
        definition = DEFAULT_LLM_PROVIDER_REGISTRY.get(provider_code)
        return getattr(settings, definition.credential_setting, None) if definition else None

    @staticmethod
    def _model_for(settings: Settings, provider_code: str) -> str:
        definition = DEFAULT_LLM_PROVIDER_REGISTRY.get(provider_code)
        return getattr(settings, definition.model_setting, settings.llm_model) if definition else settings.llm_model

    @staticmethod
    def _build_model(settings: Settings, spec: LLMModelSpec) -> LLMProvider:
        max_tokens = min(settings.llm_max_tokens, spec.max_output_tokens)
        builders = {
            "openai": lambda: OpenAIProvider(
                settings.openai_api_key,
                spec.model_id,
                settings.llm_temperature,
                max_tokens,
                spec.request_timeout_seconds,
            ),
            "anthropic": lambda: AnthropicProvider(
                settings.anthropic_api_key,
                spec.model_id,
                settings.llm_temperature,
                max_tokens,
                spec.request_timeout_seconds,
            ),
            "gemini": lambda: GeminiProvider(
                settings.google_ai_api_key,
                spec.model_id,
                settings.llm_temperature,
                max_tokens,
                spec.request_timeout_seconds,
            ),
            "vertex": lambda: VertexProvider(
                settings.vertex_project,
                settings.vertex_location,
                spec.model_id,
                settings.llm_temperature,
                max_tokens,
                spec.request_timeout_seconds,
                enabled=settings.vertex_enabled,
                service_account_email=settings.vertex_service_account_email,
                service_account_json=settings.google_service_account_json,
            ),
        }
        try:
            return builders[spec.provider]()
        except KeyError as exc:
            raise UnsupportedLLMProviderError("Fournisseur IA non pris en charge") from exc

    @staticmethod
    def create_gateway(settings: Settings) -> LLMProvider:
        """Phase 32 : construit le Resilient AI Gateway (primaire + fallbacks).

        Les fallbacks non configurés (pas de clé API) sont ignorés
        silencieusement — jamais de crash de l'application pour un fallback
        optionnel absent. Le primaire est toujours inclus (une mauvaise
        configuration du primaire doit rester visible, pas masquée).
        """

        configured_order = [
            code.casefold()
            for code in (
                settings.ai_primary_provider,
                settings.ai_fallback_provider_1,
                settings.ai_fallback_provider_2,
            )
            if code
        ]
        # Explicit fallback order remains authoritative. Any other provider
        # with a configured key is appended so all available capabilities are
        # active without requiring operators to maintain a second list.
        order = configured_order + [
            code for code in DEFAULT_LLM_PROVIDER_REGISTRY.codes()
            if code not in configured_order
        ]
        seen: set[str] = set()
        model_lists: dict[str, tuple[str, ...]] = {}
        for index, code in enumerate(order):
            if code in seen or code not in LLMProviderFactory._BUILDERS:
                continue
            if index > 0 and not LLMProviderFactory._credential_for(settings, code):
                logger.info(
                    "ai_provider_config provider=%s role=fallback position=%d credential_configured=false model=%s included=false",
                    code,
                    index,
                    LLMProviderFactory._model_for(settings, code),
                )
                continue
            seen.add(code)
            configured_models = {
                provider.casefold(): tuple(dict.fromkeys(model_ids))
                for provider, model_ids in settings.ai_provider_models.items()
            }
            model_ids = configured_models.get(code, (LLMProviderFactory._model_for(settings, code),))
            if not model_ids:
                logger.info(
                    "ai_provider_config provider=%s role=%s position=%d included=false reason=no_models",
                    code,
                    "primary" if index == 0 else "fallback",
                    index,
                )
                continue
            model_lists[code] = model_ids
            logger.info(
                "ai_provider_config provider=%s role=%s position=%d credential_configured=%s models=%s included=true",
                code,
                "primary" if index == 0 else "fallback",
                index,
                str(bool(LLMProviderFactory._credential_for(settings, code))).lower(),
                ",".join(model_ids),
            )
        rate_card = LLMRateCard.from_models(
            model_lists,
            settings.ai_model_rate_card,
            settings.ai_model_catalog,
        )
        specs = tuple(
            rate_card.spec_for(provider, model_id)
            for provider, model_ids in model_lists.items()
            for model_id in model_ids
        )
        registry = LLMModelRegistry(specs)
        active_specs = registry.list_all(enabled_only=True)
        providers = [LLMProviderFactory._build_model(settings, spec) for spec in active_specs]
        for spec in specs:
            logger.info(
                "ai_model_registry provider=%s model=%s enabled=%s capabilities=%s context_window=%d max_output_tokens=%d timeout_seconds=%s cost_class=%s latency_class=%s",
                spec.provider,
                spec.model_id,
                str(spec.enabled).lower(),
                ",".join(sorted(capability.value for capability in spec.capabilities)),
                spec.context_window,
                spec.max_output_tokens,
                spec.request_timeout_seconds,
                spec.estimated_cost_class,
                spec.latency_class,
            )
        health_registry = get_provider_health_registry()
        router = SmartModelRouter(
            {(spec.provider, spec.model_id): spec for spec in specs},
            health_registry,
        )
        breaker = get_circuit_breaker()
        breaker.configure(settings.ai_gateway_circuit_failure_threshold, settings.ai_gateway_circuit_cooldown_seconds)
        return AvenqoAIGateway(
            providers,
            circuit_breaker=breaker,
            health_registry=health_registry,
            router=router,
            rate_card=rate_card,
            max_retries_per_provider=settings.ai_gateway_max_retries,
            base_delay_seconds=settings.ai_gateway_base_delay_seconds,
            max_delay_seconds=settings.ai_gateway_max_delay_seconds,
        )