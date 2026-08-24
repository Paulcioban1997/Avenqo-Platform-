"""Service d'usage IA Avenqo : compteurs par tenant, indépendants du fournisseur LLM.

Toute logique de comptage passe par ce service — jamais directement par
`ChatService` ou par un fournisseur LLM — afin que l'agrégation reste unique
et indépendante d'OpenAI/Anthropic/Gemini (Exigence Phase 31 : suivi d'usage
"provider-independent").
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.ai.usage.exceptions import AIQuotaExceededError
from backend.app.ai.usage.policy import (
    MONTHLY_AI_REQUESTS,
    MONTHLY_LLM_TOKENS,
    MONTHLY_PREDICTIVE_REQUESTS,
    MONTHLY_TOOL_CALLS,
    AIQuotaPolicy,
)
from backend.app.models.ai_usage import TenantAIUsage
from backend.app.models.enterprise_override import EnterpriseOverride

_DEFAULT_PLAN = "demo"


class AIUsageService:
    """Vérifie et incrémente l'usage IA d'un tenant pour la période courante."""

    def __init__(self, db: Session, policy: AIQuotaPolicy) -> None:
        self._db = db
        self._policy = policy

    def current_billing_period(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m")

    def _get_or_create(self, company_id: UUID, plan_code: str | None) -> TenantAIUsage:
        period = self.current_billing_period()
        usage = (
            self._db.query(TenantAIUsage)
            .filter(TenantAIUsage.company_id == company_id, TenantAIUsage.billing_period == period)
            .one_or_none()
        )
        if usage is None:
            usage = TenantAIUsage(
                company_id=company_id,
                billing_period=period,
                subscription_plan=plan_code or _DEFAULT_PLAN,
            )
            self._db.add(usage)
            self._db.flush()
        elif plan_code is not None and usage.subscription_plan != plan_code:
            usage.subscription_plan = plan_code
        return usage

    def get_usage(self, company_id: UUID, plan_code: str | None) -> TenantAIUsage:
        """Lecture seule de l'usage courant (sans incrément)."""

        return self._get_or_create(company_id, plan_code)

    def ensure_quota_available(self, company_id: UUID, plan_code: str | None) -> None:
        """Vérifie le quota `monthly_ai_requests` AVANT tout appel LLM/outil.

        Ne lève jamais l'erreur brute d'un fournisseur : uniquement
        `AIQuotaExceededError`, un message sûr et générique.
        """

        usage = self._get_or_create(company_id, plan_code)
        limit = self.limit_for(company_id, plan_code, MONTHLY_AI_REQUESTS)
        if limit is not None and usage.ai_requests_count >= limit:
            raise AIQuotaExceededError("Your current Avenqo AI usage limit has been reached.")

    def limit_for(self, company_id: UUID, plan_code: str | None, metric: str) -> int | None:
        """Résout la limite effective : dérogation Enterprise (Phase 33) en priorité,
        sinon la politique de plan par défaut (`AIQuotaPolicy`)."""

        override = self._db.scalar(
            select(EnterpriseOverride).where(EnterpriseOverride.company_id == company_id)
        )
        if override is not None and metric in (override.quota_overrides or {}):
            value = override.quota_overrides[metric]
            return None if value is None else int(value)
        return self._policy.limit_for(plan_code, metric)

    def record_usage(
        self,
        company_id: UUID,
        plan_code: str | None,
        *,
        tokens: int = 0,
        tool_calls: int = 0,
        predictive_requests: int = 0,
    ) -> TenantAIUsage:
        """Incrémente les compteurs APRÈS un appel IA réussi."""

        usage = self._get_or_create(company_id, plan_code)
        usage.ai_requests_count += 1
        usage.llm_tokens_count += max(tokens, 0)
        usage.tool_calls_count += max(tool_calls, 0)
        usage.predictive_requests_count += max(predictive_requests, 0)
        self._db.flush()
        return usage


def tokens_from_usage(token_usage: dict[str, object]) -> int:
    """Additionne les tokens input/output d'un `token_usage` de provider, sans hypothèse de format."""

    total = 0
    for key in ("input_tokens", "output_tokens"):
        value = token_usage.get(key)
        if isinstance(value, int):
            total += value
    return total


__all__ = [
    "AIUsageService",
    "AIQuotaExceededError",
    "AIQuotaPolicy",
    "MONTHLY_AI_REQUESTS",
    "MONTHLY_LLM_TOKENS",
    "MONTHLY_TOOL_CALLS",
    "MONTHLY_PREDICTIVE_REQUESTS",
    "tokens_from_usage",
]
