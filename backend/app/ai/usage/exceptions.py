"""Exceptions du sous-système de quotas d'usage IA Avenqo.

`AIQuotaExceededError` est la SEULE exception que le reste de l'application
doit voir remonter d'un dépassement de quota : elle ne doit jamais exposer de
détails internes (fournisseur LLM, coûts, tokens exacts, autres tenants).
"""

from __future__ import annotations


class AIQuotaExceededError(RuntimeError):
    """Levée quand un tenant dépasse une limite d'usage IA configurée."""
