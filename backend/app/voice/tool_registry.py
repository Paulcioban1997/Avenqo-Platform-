"""Voice tool intersection: registered ∩ plan ∩ subscription ∩ active ∩ granted ∩ rbac ∩ scope."""

from __future__ import annotations

from backend.app.assistants.registry import AssistantRegistry
from backend.app.core.permissions import is_executive_role, normalize_role, permissions_for
from backend.app.models import CompanyMembership
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from backend.app.services.voice_module_permission_service import VoiceModulePermissionService
from backend.app.voice.caller_scope import is_public_voice_caller, public_voice_tool_allowed
from backend.app.voice.module_actions import (
    VOICE_EXECUTIVE_NATIVE_TOOLS,
    VOICE_NATIVE_TOOLS,
    VOICE_RETAIL_NATIVE_TOOLS,
    VOICE_WRITE_TOOLS,
    action_for_tool,
)
from shared.ai_engine.contracts import TenantContext
from sqlalchemy import select
from sqlalchemy.orm import Session


class VoiceToolRegistryService:
    def __init__(self, session: Session, agents: AssistantRegistry) -> None:
        self._session = session
        self._agents = agents
        self._entitlements = ModuleEntitlementService(session)
        self._grants = VoiceModulePermissionService(session)

    def allowed_tools(
        self,
        tenant: TenantContext,
        permissions: frozenset[str] | set[str] | tuple[str, ...] = frozenset(),
        *,
        granted_voice_tools: frozenset[str] | None = None,
        active_modules: frozenset[str] | None = None,
    ) -> tuple[frozenset[str], dict[str, str]]:
        perms = frozenset(permissions)
        public_caller = is_public_voice_caller(perms)
        if active_modules is None:
            self._grants.revoke_inactive_or_disallowed(tenant)
            active = frozenset(self._entitlements.get_active_modules(tenant))
        else:
            active = active_modules
        if "voice" not in active:
            return frozenset(), {}
        if granted_voice_tools is None:
            granted_tools = self._grants.granted_tools(tenant.company_id)
        else:
            granted_tools = granted_voice_tools

        write_allowed = "crm:appointments:write" in perms
        membership = None
        if tenant.user_id is not None:
            membership = self._session.scalar(
                select(CompanyMembership).where(
                    CompanyMembership.user_id == tenant.user_id,
                    CompanyMembership.company_id == tenant.company_id,
                    CompanyMembership.is_active.is_(True),
                )
            )
            if membership is not None:
                write_allowed = write_allowed or ("crm:appointments:write" in permissions_for(membership.role))

        from backend.app.services.company_intelligence_service import CompanyIntelligenceService, BOOKING_TOOLS
        intel_profile = CompanyIntelligenceService(self._session).get_profile(tenant.company_id)
        has_crm_booking = intel_profile.has_crm_booking
        has_retail_commerce = intel_profile.has_retail_commerce
        has_documents = bool(getattr(intel_profile, "has_public_documents", False))
        from backend.app.services.voice_onboarding_service import stored_business_profile
        business = stored_business_profile(self._session, tenant.company_id)

        names: set[str] = set()
        owners: dict[str, str] = {}
        if public_caller:
            names.add("get_business_info")
            owners["get_business_info"] = "voice"
            if has_retail_commerce and "retail" in active:
                names.add("search_products")
                owners["search_products"] = "voice"
        elif tenant.user_id is not None:
            # Universal generative voice intelligence tools for authenticated staff
            from backend.app.config.settings import get_settings
            from backend.app.models.voice import VoiceBusinessConfig
            from backend.app.models.company import Company
            from backend.app.models.user import User
            from backend.app.models.base import CompanyStatus, UserRole

            company_obj = self._session.get(Company, tenant.company_id)
            company_status_str = str(getattr(company_obj, "status", "")).lower()
            company_active = company_obj is not None and (
                company_status_str in {"active", "companystatus.active"}
                or getattr(company_obj, "status", None) == CompanyStatus.ACTIVE
            )
            user_obj = self._session.get(User, tenant.user_id)
            user_active = user_obj is not None and getattr(user_obj, "is_active", True)
            membership_active = membership is not None and bool(getattr(membership, "is_active", False))

            if company_active and user_active and membership_active:
                names.add("get_business_info")
                owners["get_business_info"] = "voice"
                names.add("get_my_identity")
                owners["get_my_identity"] = "voice"
                names.add("list_enabled_modules")
                owners["list_enabled_modules"] = "voice"
                if has_retail_commerce and "retail" in active:
                    for retail_native in VOICE_RETAIL_NATIVE_TOOLS:
                        names.add(retail_native)
                        owners[retail_native] = "voice"

                user_role = getattr(membership, "role", None) or getattr(user_obj, "role", None)
                canonical_role = normalize_role(user_role)
                if is_executive_role(canonical_role):
                    if has_retail_commerce and "retail" in active:
                        names.add("get_product_margins")
                        owners["get_product_margins"] = "voice"

            coach_globally_enabled = getattr(get_settings(), "voice_ai_coach_enabled", True)
            voice_cfg = self._session.scalar(
                select(VoiceBusinessConfig).where(VoiceBusinessConfig.company_id == tenant.company_id)
            )
            coach_tenant_enabled = getattr(voice_cfg, "ai_coach_enabled", True) if voice_cfg is not None else True

            if coach_globally_enabled and coach_tenant_enabled and company_active and user_active and membership_active:
                for coach_read_tool in (
                    "get_my_daily_briefing",
                    "get_my_tasks",
                    "get_coaching_advice",
                    "optimize_task_execution",
                ):
                    names.add(coach_read_tool)
                    owners[coach_read_tool] = "voice"

                user_role = getattr(membership, "role", None) or getattr(user_obj, "role", None)
                if is_executive_role(user_role):
                    names.add("get_executive_briefing")
                    owners["get_executive_briefing"] = "voice"

                # Check write permission for mark_my_task_completed
                user_perms = set(perms or ())
                if user_role:
                    user_perms.update(permissions_for(user_role))
                has_task_write = bool(
                    {"tasks:own", "tasks:write", "workspace:tasks:write"} & user_perms
                )
                if has_task_write and normalize_role(user_role) != UserRole.VIEWER.value:
                    names.add("mark_my_task_completed")
                    owners["mark_my_task_completed"] = "voice"
        for defn in self._agents.list_authorized(active):
            if defn.category in {"platform", "platform_support"} or defn.slug in {
                "tenant_capabilities",
                "platform_support",
                "voice",
            }:
                continue
            for tool_name in defn.allowed_tool_names:
                if tool_name in BOOKING_TOOLS and not has_crm_booking:
                    continue
                if tool_name == "get_subscription_options":
                    continue
                if public_caller and not public_voice_tool_allowed(
                    tool_name,
                    has_crm_booking=has_crm_booking,
                    has_retail_commerce=has_retail_commerce,
                    has_documents=has_documents,
                ):
                    continue
                mapping = action_for_tool(tool_name)
                if tool_name in VOICE_NATIVE_TOOLS:
                    # Voice-native tools are authorized exclusively in the dedicated
                    # caller/RBAC/module gate block above; never bypass via module assistants.
                    continue
                if business and business.get("allowed_actions"):
                    if not mapping or f"{mapping[0]}:{mapping[1]}" not in business.get("allowed_actions", []):
                        continue
                if (
                    mapping
                    and (mapping[0] in {"accounting", "marketing", "cross_agent"} or mapping == ("crm", "read_crm_metrics"))
                    and "data:read" not in perms
                ):
                    continue
                if tool_name not in granted_tools:
                    continue
                if tool_name in VOICE_WRITE_TOOLS and not write_allowed and not public_caller:
                    continue
                names.add(tool_name)
                owners[tool_name] = defn.agent_id
        return frozenset(names), owners


__all__ = ["VoiceToolRegistryService"]
