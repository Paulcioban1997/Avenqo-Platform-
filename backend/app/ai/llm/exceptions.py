class LLMProviderError(RuntimeError):
    """Raised when a configured LLM provider cannot complete a request."""


class UnsupportedLLMProviderError(LLMProviderError):
    """Raised when the configured LLM provider is not supported."""


class ToolCallingUnsupportedError(LLMProviderError):
    """Raised when a provider does not support tool/function calling."""