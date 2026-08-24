"""Suivi de santé par fournisseur LLM (Phase 32) — observabilité interne uniquement.

Jamais exposé au frontend/utilisateur final : sert uniquement à un futur
tableau de bord d'administration et aux logs structurés du Gateway.
"""

from __future__ import annotations

from enum import Enum


class ProviderHealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    RATE_LIMITED = "rate_limited"
    UNKNOWN = "unknown"


class ProviderHealthRegistry:
    def __init__(self) -> None:
        self._status: dict[str, ProviderHealthStatus] = {}

    def record_success(self, provider: str) -> None:
        self._status[provider] = ProviderHealthStatus.HEALTHY

    def record_failure(self, provider: str, category) -> None:
        from backend.app.ai.llm.failure_classification import FailureCategory

        if category == FailureCategory.RATE_LIMITED:
            self._status[provider] = ProviderHealthStatus.RATE_LIMITED
        elif category in (FailureCategory.AUTH_CONFIG, FailureCategory.INVALID_REQUEST):
            self._status[provider] = ProviderHealthStatus.UNAVAILABLE
        else:
            self._status[provider] = ProviderHealthStatus.DEGRADED

    def status_for(self, provider: str) -> ProviderHealthStatus:
        return self._status.get(provider, ProviderHealthStatus.UNKNOWN)

    def snapshot(self) -> dict[str, str]:
        return {provider: status.value for provider, status in self._status.items()}


_global_registry = ProviderHealthRegistry()


def get_provider_health_registry() -> ProviderHealthRegistry:
    return _global_registry
