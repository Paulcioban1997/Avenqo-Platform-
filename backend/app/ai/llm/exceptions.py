class LLMProviderError(RuntimeError):
    """Raised when a configured LLM provider cannot complete a request."""


class UnsupportedLLMProviderError(LLMProviderError):
    """Raised when the configured LLM provider is not supported."""


class ToolCallingUnsupportedError(LLMProviderError):
    """Raised when a provider does not support tool/function calling."""


class AIProvidersUnavailableError(LLMProviderError):
    """Phase 32 : levée quand TOUS les fournisseurs configurés (primaire + fallbacks)
    ont échoué ou ont leur circuit ouvert. Jamais de détail fournisseur/clé API
    dans le message — `ChatService` la traduit en `AIServiceUnavailableError`."""