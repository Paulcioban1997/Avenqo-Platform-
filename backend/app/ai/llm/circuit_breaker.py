"""Circuit breaker par fournisseur LLM (Phase 32).

Instance en mémoire, partagée pour tout le process via `get_circuit_breaker()`
(comme `get_settings()` — un singleton par process, pas distribué entre
workers : limitation documentée, acceptable pour cette phase). Après
`failure_threshold` échecs consécutifs pour un fournisseur, son circuit
s'ouvre et il est temporairement sauté par `AvenqoAIGateway` ; après
`cooldown_seconds`, une tentative de sonde (half-open) est de nouveau permise.
"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class _ProviderState:
    consecutive_failures: int = 0
    opened_at: float | None = None


class ProviderCircuitBreaker:
    def __init__(self, failure_threshold: int = 3, cooldown_seconds: float = 30.0) -> None:
        self._threshold = failure_threshold
        self._cooldown = cooldown_seconds
        self._states: dict[str, _ProviderState] = {}

    def configure(self, failure_threshold: int, cooldown_seconds: float) -> None:
        """Met à jour les seuils sans réinitialiser l'état courant des fournisseurs."""

        self._threshold = failure_threshold
        self._cooldown = cooldown_seconds

    def _state(self, provider: str) -> _ProviderState:
        return self._states.setdefault(provider, _ProviderState())

    def is_open(self, provider: str) -> bool:
        state = self._state(provider)
        if state.opened_at is None:
            return False
        if time.monotonic() - state.opened_at >= self._cooldown:
            # Cooldown écoulé : on autorise une sonde (half-open) avant de rouvrir.
            state.opened_at = None
            state.consecutive_failures = 0
            return False
        return True

    def record_success(self, provider: str) -> None:
        state = self._state(provider)
        state.consecutive_failures = 0
        state.opened_at = None

    def record_failure(self, provider: str) -> None:
        state = self._state(provider)
        state.consecutive_failures += 1
        if state.consecutive_failures >= self._threshold and state.opened_at is None:
            state.opened_at = time.monotonic()

    def status_for(self, provider: str) -> str:
        return "open" if self.is_open(provider) else "closed"


_global_breaker = ProviderCircuitBreaker()


def get_circuit_breaker() -> ProviderCircuitBreaker:
    return _global_breaker
