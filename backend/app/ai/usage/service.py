"""Service d'usage IA Avenqo : compteurs et crédits par tenant."""

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
from backend.app.services.ai_credit_service import AICreditService

_DEFAULT_PLAN = "demo"
_CREDITS_PER_SUCCESSFUL_AI_REQUEST = 1


class AIUsageService:
    """Vérifie puis incrémente l'usage IA d'un tenant pour la période courante."""

    def __init__(self, db: Session, policy: AIQuotaPolicy) -> None:
        self._db = db
        self._policy = policy
        self._credits = AICreditService(db)

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
        return self._get_or_create(company_id, plan_code)

    def ensure_quota_available(self, company_id: UUID, plan_code: str | None) -> None:
        """Vérifie quotas et crédits avant tout appel IA payant."""

        effective_plan = plan_code or _DEFAULT_PLAN
        usage = self._get_or_create(company_id, effective_plan)
        limit = self.limit_for(company_id, effective_plan, MONTHLY_AI_REQUESTS)
        if limit is not None and usage.ai_requests_count >= limit:
            raise AIQuotaExceededError("Your current Avenqo AI usage limit has been reached.")
        self._credits.ensure_available(
            company_id,
            effective_plan,
            _CREDITS_PER_SUCCESSFUL_AI_REQUEST,
        )

    def limit_for(self, company_id: UUID, plan_code: str | None, metric: str) -> int | None:
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
        """Compte l'usage et débite un crédit uniquement après un appel IA réussi."""

        effective_plan = plan_code or _DEFAULT_PLAN
        usage = self._get_or_create(company_id, effective_plan)
        self._credits.consume(
            company_id,
            effective_plan,
            _CREDITS_PER_SUCCESSFUL_AI_REQUEST,
        )
        usage.ai_requests_count += 1
        usage.llm_tokens_count += max(tokens, 0)
        usage.tool_calls_count += max(tool_calls, 0)
        usage.predictive_requests_count += max(predictive_requests, 0)
        self._db.flush()
        return usage


def tokens_from_usage(token_usage: dict[str, object]) -> int:
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
