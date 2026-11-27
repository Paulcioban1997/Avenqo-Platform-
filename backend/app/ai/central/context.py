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
    company_profile: dict[str, object] = field(default_factory=dict)
    caller_identity: dict[str, object] | None = None
    enabled_module_details: tuple[dict[str, str], ...] = ()

    def as_capabilities(self) -> dict[str, object]:
        return {
            "tenant_id": str(self.tenant.company_id),
            "company_profile": self.company_profile,
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
        from backend.app.voice.caller_scope import is_public_voice_caller
        if is_public_voice_caller(self.permissions):
            return json.dumps({"company_profile": self.company_profile, "conversation_language": self.user_language,
                               "timezone": self.company_timezone, "caller_scope": "public", "personal_authentication_required_for_private_data": True},
                              separators=(",", ":")).replace("<", chr(92) + "u003c")
        return json.dumps(
            {
                "tenant_id": str(self.tenant.company_id),
                "company_profile": self.company_profile,
                "plan_code": self.plan_code,
                "subscription_status": self.subscription_status,
                "permissions": sorted(self.permissions),
                "timezone": self.company_timezone,
                "active_modules": self.active_modules,
                "enabled_module_details": list(self.enabled_module_details),
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
                "caller_identity": self.caller_identity,
            },
            separators=(",", ":"),
        ).replace("<", chr(92) + "u003c")


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
        company_profile = {}
        caller_identity = None
        session = getattr(self._entitlements, "_session", None)
        if session is not None:
            from sqlalchemy import select
            from backend.app.models.user import User
            from backend.app.models.company_membership import CompanyMembership
            from backend.app.services.company_intelligence_service import CompanyIntelligenceService
            from backend.app.voice.caller_scope import is_public_voice_caller
            company_profile = CompanyIntelligenceService(session).get_profile(tenant.company_id, selected_tenant=TenantContext(tenant.company_id, user_id)).as_context(public=is_public_voice_caller(permissions) or "data:read" not in permissions)
            if user_id is not None and not is_public_voice_caller(permissions):
                from backend.app.core.permissions import is_executive_role, normalize_role
                actor = session.get(User, user_id)
                if actor is not None and actor.company_id == tenant.company_id:
                    membership = session.scalar(
                        select(CompanyMembership).where(
                            CompanyMembership.user_id == user_id,
                            CompanyMembership.company_id == tenant.company_id,
                            CompanyMembership.is_active.is_(True),
                        )
                    )
                    role_val = normalize_role(
                        membership.role if membership is not None else None
                    ) or "member"
                    # A user's account role alone does not establish active tenant membership.
                    verified_exec = bool(
                        membership is not None
                        and is_executive_role(role_val)
                        and "data:read" in permissions
                    )
                    caller_identity = {
                        "user_id": str(user_id),
                        "full_name": f"{actor.first_name or ''} {actor.last_name or ''}".strip() or actor.first_name or "Collaborateur",
                        "first_name": actor.first_name or "",
                        "role": role_val,
                        "is_executive_role": verified_exec,
                        "can_view_margins": verified_exec,
                        "job_title": actor.job_title or "",
                    }
        # Security boundary: never place private supplier costs or margins in
        # the model's prompt for a public caller or non-executive staff member.
        # Tool-level denials cannot undo an already-exposed prompt field.
        can_see_margins = bool(caller_identity and caller_identity.get("can_view_margins"))
        if not can_see_margins:
            margin_fields = {"unit_cost", "profit_margin_amount", "profit_margin_pct", "profit_margin", "gross_margin", "cost_price", "cogs"}
            products = company_profile.get("public_products")
            if isinstance(products, (tuple, list)):
                company_profile = {
                    **company_profile,
                    "public_products": tuple(
                        {k: v for k, v in row.items() if k not in margin_fields}
                        if isinstance(row, dict) else row
                        for row in products
                    ),
                }
        from backend.app.ai.tools.business.voice_intelligence_tools import MODULE_CAPABILITY_DESCRIPTIONS
        enabled_mod_details = tuple(
            {
                "key": m.key,
                "name": m.display_name or MODULE_CAPABILITY_DESCRIPTIONS.get(m.key, {}).get("name", m.key),
                "purpose": MODULE_CAPABILITY_DESCRIPTIONS.get(m.key, {}).get("purpose", ""),
            }
            for m in summary.modules
            if m.active
        )
        return CentralAIContext(
            company_profile=company_profile,
            caller_identity=caller_identity,
            enabled_module_details=enabled_mod_details,
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
            authorized_sources=self._sources(tenant) if self._sources is not None and "data:read" in permissions else {},
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
