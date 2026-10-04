"""Classification des échecs fournisseur LLM (Phase 32).

Ne jamais fallback aveuglément sur toute erreur : seules les catégories
"temporaires" (timeout, réseau, 5xx, rate limit, surcharge, inconnu) sont
éligibles au fallback/retry. Une erreur de configuration (clé API absente),
une requête invalide, ou un rejet de contenu doivent échouer clairement au
lieu d'être masqués par un basculement silencieux vers un autre fournisseur.

Les providers existants (Phase 28) enveloppent toute exception dans un
`LLMProviderError` générique tout en préservant la cause originale via
`raise ... from exc` : la classification inspecte donc `exc.__cause__`
lorsqu'il existe.
"""

from __future__ import annotations

from enum import Enum


class FailureCategory(str, Enum):
    TIMEOUT = "timeout"
    NETWORK = "network"
    PROVIDER_5XX = "provider_5xx"
    RATE_LIMITED = "rate_limited"
    OVERLOADED = "overloaded"
    AUTH_CONFIG = "auth_config"
    INVALID_REQUEST = "invalid_request"
    CONTENT_REJECTED = "content_rejected"
    QUOTA_PROBLEM = "quota_problem"
    USAGE_UNAVAILABLE = "usage_unavailable"
    MODEL_UNAVAILABLE = "model_unavailable"
    UNKNOWN = "unknown"


# Catégories pour lesquelles basculer vers un autre fournisseur est sûr.
# NOTE : QUOTA_PROBLEM (crédit/quota épuisé chez UN fournisseur) est
# volontairement éligible au fallback — c'est précisément le scénario que le
# Resilient AI Gateway (Phase 32) doit gérer : un épuisement de crédit chez
# le fournisseur primaire ne doit jamais bloquer les fournisseurs de secours
# configurés. Seul un épuisement de quota sur TOUS les fournisseurs
# (dernier de la liste) doit remonter une erreur visible à l'utilisateur.
_FALLBACK_ELIGIBLE = frozenset({
    FailureCategory.TIMEOUT,
    FailureCategory.NETWORK,
    FailureCategory.PROVIDER_5XX,
    FailureCategory.RATE_LIMITED,
    FailureCategory.OVERLOADED,
    FailureCategory.QUOTA_PROBLEM,
    FailureCategory.UNKNOWN,
    FailureCategory.MODEL_UNAVAILABLE,
})

# Catégories pour lesquelles réessayer le MÊME fournisseur peut résoudre le problème.
_RETRYABLE = frozenset({
    FailureCategory.TIMEOUT,
    FailureCategory.NETWORK,
    FailureCategory.PROVIDER_5XX,
    FailureCategory.OVERLOADED,
})


def classify_exception(exc: BaseException) -> FailureCategory:
    """Classification par heuristique de message — jamais de détail exposé au LLM/client."""

    text = f"{type(exc).__name__} {exc}".lower()

    if "usage metadata unavailable" in text:
        return FailureCategory.USAGE_UNAVAILABLE
    if any(marker in text for marker in ("credit balance", "insufficient balance", "insufficient_quota", "billing")):
        return FailureCategory.QUOTA_PROBLEM
    status_code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if status_code in (401, 403):
        return FailureCategory.AUTH_CONFIG
    if status_code == 404:
        return FailureCategory.MODEL_UNAVAILABLE
    if status_code == 429:
        return FailureCategory.RATE_LIMITED
    if status_code == 503:
        return FailureCategory.OVERLOADED
    if isinstance(status_code, int) and 500 <= status_code <= 599:
        return FailureCategory.PROVIDER_5XX
    if "timeout" in text or "timed out" in text:
        return FailureCategory.TIMEOUT
    if ("rate" in text and "limit" in text) or "429" in text or "ratelimit" in text:
        return FailureCategory.RATE_LIMITED
    if any(marker in text for marker in ("api key", "authentication", "unauthorized", "401", "403", "n'est pas configuré", "n'est pas configure", "dépendance", "not installed", "defaultcredentialserror", "refresherror")):
        return FailureCategory.AUTH_CONFIG
    if "overloaded" in text or "503" in text or "service unavailable" in text:
        return FailureCategory.OVERLOADED
    if any(code in text for code in ("500", "502", "504", "internal server error", "bad gateway", "gateway timeout")):
        return FailureCategory.PROVIDER_5XX
    if any(marker in text for marker in ("connection", "network", "dns", "unreachable")):
        return FailureCategory.NETWORK
    if any(marker in text for marker in ("content polic", "content_polic", "safety", "moderat", "reject")):
        return FailureCategory.CONTENT_REJECTED
    if any(marker in text for marker in ("quota", "insufficient_quota", "billing")):
        return FailureCategory.QUOTA_PROBLEM
    if any(marker in text for marker in ("invalid", "400", "bad request", "validation")):
        return FailureCategory.INVALID_REQUEST
    if isinstance(status_code, int) and 400 <= status_code <= 499:
        return FailureCategory.INVALID_REQUEST
    return FailureCategory.UNKNOWN


def is_retryable(category: FailureCategory) -> bool:
    return category in _RETRYABLE


def is_fallback_eligible(category: FailureCategory) -> bool:
    return category in _FALLBACK_ELIGIBLE
