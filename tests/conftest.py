"""Fixtures partagées pour l'ensemble de la suite de tests.

Phase 34 : réinitialise le limiteur de débit (rate limiter) en mémoire avant
CHAQUE test. Sans cela, l'état cumulatif du singleton module-level
`backend.app.core.rate_limit._limiter` persisterait entre tous les tests
exécutés dans le même processus pytest, provoquant des `429` inattendus dans
des tests qui appellent une route protégée plusieurs fois (ex. `/auth/login`)
sans rapport avec le rate limiting lui-même.
"""

from __future__ import annotations

import pytest

from backend.app.core.rate_limit import reset_rate_limiter


@pytest.fixture(autouse=True)
def _reset_rate_limiter_between_tests():
    reset_rate_limiter()
    yield
    reset_rate_limiter()
