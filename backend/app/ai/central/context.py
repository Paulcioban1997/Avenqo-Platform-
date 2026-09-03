"""Trusted, tenant-scoped context for Central AI requests."""

from __future__ import annotations

from dataclasses import dataclass
import json
from uuid import UUID

from backend.app.ai.usage.service import AIUsageService
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from shared.ai_engine.contracts import TenantContext


@dataclass(frozen=True, slots=True)
class CentralAIContext:
    tenant: TenantContext
    user_id: UUID
    permissions: frozenset[str]
    plan_code: str
    active_modules: tuple[str, ...]
    authorized_modules: tuple[str, ...]
    module_limit: int | None
    remaining_module_slots: int | None
    ai_credit_balance: dict[str, int | str | None]
    premium_modules: tuple[str, ...]
    user_language: str
    company_country: str
    company_currency: str
    company_timezone: str

    def as_prompt_context(self) -> str:
        return json.dumps(
            {
                "plan_code": self.plan_code,
                "active_modules": self.active_modules,
                "authorized_modules": self.authorized_modules,
                "module_limit": self.module_limit,
                "remaining_module_slots": self.remaining_module_slots,
                "ai_credit_balance": self.ai_credit_balance,
                "premium_modules": self.premium_modules,
            },
            separators=(",", ":"),
        )


class CentralAIContextBuilder:
    def __init__(
        self,
        entitlements: ModuleEntitlementService,
        usage: AIUsageService,
    ) -> None:
        self._entitlements = entitlements
        self._usage = usage

    def build(
        self,
        tenant: TenantContext,
        user_id: UUID,
        *,
        permissions: frozenset[str],
        user_language: str,
        company_country: str,
        company_currency: str,
        company_timezone: str,
    ) -> CentralAIContext:
        summary = self._entitlements.summary(tenant)
        authorized = tuple(
            module.key
            for module in summary.modules
            if module.state.value in {"active", "available", "limit_reached"}
        )
        premium = tuple(module.key for module in summary.modules if module.premium)
        return CentralAIContext(
            tenant=tenant,
            user_id=user_id,
            permissions=permissions,
            plan_code=summary.plan_code,
            active_modules=summary.active_modules,
            authorized_modules=authorized,
            module_limit=summary.module_limit,
            remaining_module_slots=summary.remaining_module_slots,
            ai_credit_balance=self._usage.get_credit_balance(
                tenant.company_id, summary.plan_code
            ),
            premium_modules=premium,
            user_language=user_language,
            company_country=company_country,
            company_currency=company_currency,
            company_timezone=company_timezone,
        )


__all__ = ["CentralAIContext", "CentralAIContextBuilder"]