from shared.ai_engine.contracts import FeatureProvider
from shared.ai_engine.exceptions import TaskNotRegisteredError


class FeatureProviderRegistry:
    """Sélectionne les fournisseurs de features selon le module métier."""

    def __init__(self) -> None:
        self._providers: dict[str, FeatureProvider] = {}

    def register(self, provider: FeatureProvider) -> None:
        self._providers[provider.module_code] = provider

    def get(self, module_code: str) -> FeatureProvider:
        try:
            return self._providers[module_code]
        except KeyError as exc:
            raise TaskNotRegisteredError(
                f"No feature provider is registered for module '{module_code}'"
            ) from exc
