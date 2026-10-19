"""Same Voice tool guard for Central AI, Telnyx media, and Retell dispatch."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.ai.usage.exceptions import AIQuotaExceededError
from backend.app.core.permissions import permissions_for
from backend.app.models import BillingAccount, CompanyMembership, User
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from backend.app.services.voice_module_permission_service import VoiceModulePermissionService
from backend.app.voice.caller_scope import is_public_voice_caller, public_voice_tool_allowed
from backend.app.voice.module_actions import (
    VOICE_TOOL_ALIASES,
    VOICE_WRITE_TOOLS,
    action_for_tool,
    is_voice_native_tool,
)
from shared.ai_engine.contracts import TenantContext


class VoiceToolDenied(PermissionError):
    """Fail-closed Voice tool refusal."""


class VoiceToolGuard:
    """Re-query grants + entitlements on every tool call. No stale cache."""

    def __init__(self, session: Session, usage_service=None) -> None:
        self._session = session
        self._usage = usage_service
        self._entitlements = ModuleEntitlementService(session)
        self._grants = VoiceModulePermissionService(session)

    def authorize(
        self,
        tenant: TenantContext,
        tool_name: str,
        permissions: frozenset[str] | set[str] | tuple[str, ...],
        *,
        user_id: UUID | None = None,
        require_credits: bool = False,
    ) -> None:
        perms = frozenset(permissions)
        public_caller = is_public_voice_caller(perms)
        if user_id is not None and not public_caller:
            user = self._session.get(User, user_id, populate_existing=True)
            membership = self._session.scalar(
                select_membership(tenant.company_id, user_id).execution_options(populate_existing=True)
            )
            if user is None or not user.is_active or user.company_id != tenant.company_id or membership is None:
                raise VoiceToolDenied("An active tenant membership is required.")
            perms = perms.intersection(permissions_for(membership.role))
        from sqlalchemy import select
        account = self._session.scalar(select(BillingAccount).where(
            BillingAccount.company_id == tenant.company_id,
        ).execution_options(populate_existing=True))
        if account is None or account.status.strip().lower() not in {"active", "trialing"}:
            raise VoiceToolDenied("An active Voice subscription is required.")
        active = set(self._entitlements.get_active_modules(tenant))
        self._grants.revoke_inactive_or_disallowed(tenant)
        if "voice" not in active:
            raise VoiceToolDenied("The Voice module is not active.")
        if require_credits and self._usage is not None:
            plan = self._entitlements.get_company_plan(tenant)
            try:
                self._usage.ensure_quota_available(tenant.company_id, plan.code.value)
            except AIQuotaExceededError as exc:
                raise VoiceToolDenied("credits_exhausted") from exc
        from backend.app.services.company_intelligence_service import CompanyIntelligenceService, BOOKING_TOOLS
        canonical = VOICE_TOOL_ALIASES.get(tool_name, tool_name)
        if canonical in BOOKING_TOOLS and not CompanyIntelligenceService(self._session).get_profile(tenant.company_id).has_crm_booking:
            raise VoiceToolDenied("No verified bookable service is configured for this company")
        if is_voice_native_tool(tool_name):
            return
        canonical = VOICE_TOOL_ALIASES.get(tool_name, tool_name)
        if public_caller and not (
            public_voice_tool_allowed(tool_name) or public_voice_tool_allowed(canonical)
        ):
            raise VoiceToolDenied("Caller authentication is required for this tool.")
        mapping = action_for_tool(tool_name)
        if mapping is None:
            raise VoiceToolDenied("Voice cannot invent or execute an unmapped tool.")
        module_code, action_code = mapping
        if (module_code in {"retail", "accounting", "marketing", "cross_agent"} or (module_code == "crm" and action_code == "read_crm_metrics")) and "data:read" not in perms:
            raise VoiceToolDenied("Private company data requires an authenticated data reader")
        plan = self._entitlements.get_company_plan(tenant)
        if module_code not in active or not plan.allows_module(module_code):
            raise VoiceToolDenied("The required subscription module is not active.")
        if not self._grants.is_granted(tenant.company_id, module_code, action_code):
            raise VoiceToolDenied("Voice permission is not granted for this action.")
        if tool_name in VOICE_WRITE_TOOLS and "crm:appointments:write" not in perms:
            if user_id is not None:
                self._assert_membership_write(tenant.company_id, user_id)
            else:
                raise VoiceToolDenied("The membership role cannot run this tool.")

    def assert_policy(self, tenant: TenantContext, tool_name: str, permissions, *, user_id: UUID | None = None) -> None:
        from backend.app.ai.tools.exceptions import ToolAuthorizationError

        try:
            self.authorize(tenant, tool_name, permissions, user_id=user_id)
        except VoiceToolDenied as exc:
            raise ToolAuthorizationError(str(exc)) from exc

    def _assert_membership_write(self, company_id: UUID, user_id: UUID) -> None:
        user = self._session.get(User, user_id)
        if user is None or not user.is_active or user.company_id != company_id:
            raise VoiceToolDenied("The authenticated user cannot access this tenant.")
        membership = self._session.scalar(
            select_membership(company_id, user_id)
        )
        if membership is None:
            raise VoiceToolDenied("An active tenant membership is required.")
        if "crm:appointments:write" not in permissions_for(membership.role):
            raise VoiceToolDenied("The membership role cannot run this tool.")


def select_membership(company_id: UUID, user_id: UUID):
    from sqlalchemy import select

    return select(CompanyMembership).where(
        CompanyMembership.user_id == user_id,
        CompanyMembership.company_id == company_id,
        CompanyMembership.is_active.is_(True),
    )


__all__ = ["VoiceToolDenied", "VoiceToolGuard"]
