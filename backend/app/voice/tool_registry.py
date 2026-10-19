"""Voice tool intersection: registered ∩ plan ∩ subscription ∩ active ∩ granted ∩ rbac ∩ scope."""

from __future__ import annotations

from backend.app.assistants.registry import AssistantRegistry
from backend.app.core.permissions import permissions_for
from backend.app.models import CompanyMembership
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from backend.app.services.voice_module_permission_service import VoiceModulePermissionService
from backend.app.voice.caller_scope import is_public_voice_caller, public_voice_tool_allowed
from backend.app.voice.module_actions import VOICE_WRITE_TOOLS, action_for_tool
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
        if not write_allowed and tenant.user_id is not None:
            membership = self._session.scalar(
                select(CompanyMembership).where(
                    CompanyMembership.user_id == tenant.user_id,
                    CompanyMembership.company_id == tenant.company_id,
                    CompanyMembership.is_active.is_(True),
                )
            )
            if membership is not None:
                write_allowed = "crm:appointments:write" in permissions_for(membership.role)

        from backend.app.services.company_intelligence_service import CompanyIntelligenceService, BOOKING_TOOLS
        has_crm_booking = CompanyIntelligenceService(self._session).get_profile(tenant.company_id).has_crm_booking

        names: set[str] = set()
        owners: dict[str, str] = {}
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
                if public_caller and not public_voice_tool_allowed(tool_name, has_crm_booking=has_crm_booking):
                    continue
                mapping = action_for_tool(tool_name)
                if mapping and (mapping[0] in {"retail", "accounting", "marketing", "cross_agent"} or mapping == ("crm", "read_crm_metrics")) and "data:read" not in perms:
                    continue
                if tool_name not in granted_tools:
                    continue
                if tool_name in VOICE_WRITE_TOOLS and not write_allowed and not public_caller:
                    continue
                names.add(tool_name)
                owners[tool_name] = defn.agent_id
        return frozenset(names), owners


__all__ = ["VoiceToolRegistryService"]
