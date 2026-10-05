"""Trusted, tenant-scoped context for Central AI requests."""

from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Callable
import json
from uuid import UUID

from backend.app.ai.usage.service import AIUsageService
from backend.app.assistants.registry import AssistantRegistry
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from payments.plans import PUBLIC_PLANS
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
    language_source: str = "fallback"
    language_confidence: float | None = None
    language_auto_detect: bool = False
    subscription_status: str = "inactive"
    available_agents: tuple[str, ...] = ()
    authorized_sources: dict[str, object] = field(default_factory=dict)
    plan_options: tuple[dict[str, object], ...] = ()

    def as_capabilities(self) -> dict[str, object]:
        return {
            "tenant_id": str(self.tenant.company_id),
            "subscription_plan": self.plan_code,
            "subscription_status": self.subscription_status,
            "enabled_modules": list(self.active_modules),
            "plan_compatible_modules": list(self.authorized_modules),
            "available_agents": list(self.available_agents),
            "permissions": sorted(self.permissions),
            "ai_credit_balance": self.ai_credit_balance,
            "locale": self.user_language,
            "timezone": self.company_timezone,
            "authorized_sources": self.authorized_sources,
            "plan_options": list(self.plan_options),
            "upgrade_route": "/billing",
            "paid_changes_require_confirmation": True,
        }

    def as_prompt_context(self) -> str:
        return json.dumps(
            {
                "tenant_id": str(self.tenant.company_id),
                "plan_code": self.plan_code,
                "subscription_status": self.subscription_status,
                "permissions": sorted(self.permissions),
                "timezone": self.company_timezone,
                "active_modules": self.active_modules,
                "authorized_modules": self.authorized_modules,
                "module_limit": self.module_limit,
                "remaining_module_slots": self.remaining_module_slots,
                "ai_credit_balance": self.ai_credit_balance,
                "premium_modules": self.premium_modules,
                "conversation_language": self.user_language,
                "language_source": self.language_source,
                "language_confidence": self.language_confidence,
                "language_auto_detect": self.language_auto_detect,
                "available_agents": self.available_agents,
                "authorized_sources": self.authorized_sources,
                "plan_options": self.plan_options,
                "upgrade_route": "/billing",
                "paid_changes_require_confirmation": True,
            },
            separators=(",", ":"),
        )


class CentralAIContextBuilder:
    def __init__(
        self,
        entitlements: ModuleEntitlementService,
        usage: AIUsageService,
        registry: AssistantRegistry | None = None,
        sources: Callable[[TenantContext], dict[str, object]] | None = None,
    ) -> None:
        self._entitlements = entitlements
        self._usage = usage
        self._registry = registry
        self._sources = sources

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
        language_source: str = "fallback",
        language_confidence: float | None = None,
        language_auto_detect: bool = False,
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
            language_source=language_source,
            language_confidence=language_confidence,
            language_auto_detect=language_auto_detect,
            subscription_status=summary.subscription_status,
            available_agents=tuple(
                agent.slug for agent in self._registry.list_authorized(frozenset(summary.active_modules))
                if agent.required_permissions.issubset(permissions)
                and agent.entrypoints.intersection({"business", "voice"})
            ) if self._registry is not None and summary.subscription_status.strip().lower() in {"active", "trialing"} else (),
            authorized_sources=self._sources(tenant) if self._sources is not None else {},
            plan_options=tuple({
                "code": plan.code.value,
                "name": plan.name,
                "selectable_modules": sorted(plan.selectable_modules),
                "module_limit": plan.max_selectable_modules,
                "requires_sales_contact": plan.requires_sales_contact,
                "monthly_price_usd": plan.monthly_price_usd,
            } for plan in PUBLIC_PLANS),
        )


TenantCapabilityContext = CentralAIContext

__all__ = ["CentralAIContext", "CentralAIContextBuilder", "TenantCapabilityContext"]