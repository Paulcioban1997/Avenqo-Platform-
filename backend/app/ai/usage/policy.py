"""Politique de quotas d'usage IA Avenqo, par plan d'abonnement.

Les limites sont entièrement configurables (variable d'environnement
`AI_QUOTA_LIMITS`, JSON) et NE contiennent aucune valeur commerciale
"inventée" par défaut : tant qu'une limite n'est pas explicitement
configurée pour un plan/métrique donné, elle est considérée comme
"non plafonnée" (`None`). Cela permet d'activer les quotas progressivement,
métrique par métrique et plan par plan, sans bloquer les tenants existants.

Métriques reconnues :
- ``monthly_ai_requests``: nombre de messages/requêtes IA par mois.
- ``monthly_llm_tokens``: total de tokens LLM (input+output) par mois.
- ``monthly_tool_calls``: nombre d'exécutions d'outils par mois.
- ``monthly_predictive_requests``: nombre d'appels à des outils prédictifs par mois.
- ``max_concurrent_ai_requests``: requêtes IA simultanées autorisées pour un tenant.
- ``max_conversation_history``: nombre de messages conservés dans l'historique envoyé au LLM.
"""

from __future__ import annotations

from backend.app.config.settings import Settings

MONTHLY_AI_REQUESTS = "monthly_ai_requests"
MONTHLY_LLM_TOKENS = "monthly_llm_tokens"
MONTHLY_TOOL_CALLS = "monthly_tool_calls"
MONTHLY_PREDICTIVE_REQUESTS = "monthly_predictive_requests"
MAX_CONCURRENT_AI_REQUESTS = "max_concurrent_ai_requests"
MAX_CONVERSATION_HISTORY = "max_conversation_history"

KNOWN_METRICS = frozenset({
    MONTHLY_AI_REQUESTS,
    MONTHLY_LLM_TOKENS,
    MONTHLY_TOOL_CALLS,
    MONTHLY_PREDICTIVE_REQUESTS,
    MAX_CONCURRENT_AI_REQUESTS,
    MAX_CONVERSATION_HISTORY,
})


class AIQuotaPolicy:
    """Résout la limite configurée pour un plan et une métrique donnés."""

    def __init__(self, settings: Settings) -> None:
        self._limits = settings.ai_quota_limits

    def limit_for(self, plan_code: str | None, metric: str) -> int | None:
        """Retourne la limite configurée, ou `None` si non plafonné (défaut)."""

        if plan_code is None:
            return None
        plan_limits = self._limits.get(plan_code, {})
        value = plan_limits.get(metric)
        if value is None:
            return None
        return int(value)
