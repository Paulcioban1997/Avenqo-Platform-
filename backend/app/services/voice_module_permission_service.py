"""Live Voice module/action grants. Empty by default; re-queried on every call."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import VoiceModulePermission
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from backend.app.voice.module_actions import (
    actions_for_module,
    catalog_modules,
    known_action,
    tools_for_action,
    tools_for_grants,
    voice_agent_language,
)
from shared.ai_engine.contracts import TenantContext


class VoiceModulePermissionError(ValueError):
    pass


class VoiceModulePermissionService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def granted_actions(self, company_id: UUID) -> set[tuple[str, str]]:
        rows = self._session.scalars(
            select(VoiceModulePermission).where(
                VoiceModulePermission.company_id == company_id,
                VoiceModulePermission.granted.is_(True),
                VoiceModulePermission.revoked_at.is_(None),
            )
        )
        return {(row.module_code, row.action_code) for row in rows}

    def granted_tools(self, company_id: UUID) -> frozenset[str]:
        return tools_for_grants(self.granted_actions(company_id))

    def is_granted(self, company_id: UUID, module_code: str, action_code: str) -> bool:
        row = self._row(company_id, module_code, action_code)
        return row is not None and row.granted is True and row.revoked_at is None

    def current_epoch(self, company_id: UUID) -> int:
        rows = self._session.scalars(
            select(VoiceModulePermission.permission_epoch).where(
                VoiceModulePermission.company_id == company_id,
            )
        )
        return max((int(value) for value in rows), default=0)

    def grant(
        self,
        tenant: TenantContext,
        module_code: str,
        action_code: str,
        *,
        granted_by: UUID | None,
    ) -> VoiceModulePermission:
        if not known_action(module_code, action_code):
            raise VoiceModulePermissionError("Unknown Voice module action.")
        entitlements = ModuleEntitlementService(self._session)
        active = set(entitlements.get_active_modules(tenant))
        plan = entitlements.get_company_plan(tenant)
        if module_code not in active or not plan.allows_module(module_code):
            raise VoiceModulePermissionError("The module is not active for Voice grants.")
        now = datetime.now(timezone.utc)
        row = self._row(tenant.company_id, module_code, action_code)
        if row is None:
            row = VoiceModulePermission(
                company_id=tenant.company_id,
                module_code=module_code,
                action_code=action_code,
                granted=True,
                granted_by=granted_by,
                granted_at=now,
                revoked_at=None,
                permission_epoch=self.current_epoch(tenant.company_id),
            )
            self._session.add(row)
        else:
            row.granted = True
            row.granted_by = granted_by
            row.granted_at = now
            row.revoked_at = None
        self._session.flush()
        return row

    def revoke(
        self,
        tenant: TenantContext,
        module_code: str,
        action_code: str,
    ) -> VoiceModulePermission | None:
        if not known_action(module_code, action_code):
            raise VoiceModulePermissionError("Unknown Voice module action.")
        row = self._row(tenant.company_id, module_code, action_code)
        if row is None:
            return None
        self._revoke_row(row)
        self._session.flush()
        return row

    def revoke_module(self, company_id: UUID, module_code: str) -> int:
        rows = list(self._session.scalars(
            select(VoiceModulePermission).where(
                VoiceModulePermission.company_id == company_id,
                VoiceModulePermission.module_code == module_code,
                VoiceModulePermission.granted.is_(True),
            )
        ))
        for row in rows:
            self._revoke_row(row)
        if rows:
            self._session.flush()
        return len(rows)

    def revoke_all(self, company_id: UUID) -> int:
        rows = list(self._session.scalars(
            select(VoiceModulePermission).where(
                VoiceModulePermission.company_id == company_id,
                VoiceModulePermission.granted.is_(True),
            )
        ))
        for row in rows:
            self._revoke_row(row)
        if rows:
            self._session.flush()
        return len(rows)

    def revoke_inactive_or_disallowed(self, tenant: TenantContext) -> int:
        entitlements = ModuleEntitlementService(self._session)
        active = set(entitlements.get_active_modules(tenant))
        plan = entitlements.get_company_plan(tenant)
        rows = list(self._session.scalars(
            select(VoiceModulePermission).where(
                VoiceModulePermission.company_id == tenant.company_id,
                VoiceModulePermission.granted.is_(True),
            )
        ))
        revoked = 0
        for row in rows:
            if row.module_code not in active or not plan.allows_module(row.module_code):
                self._revoke_row(row)
                revoked += 1
        if revoked:
            self._session.flush()
        return revoked

    def list_settings(self, tenant: TenantContext, *, config=None) -> dict[str, object]:
        entitlements = ModuleEntitlementService(self._session)
        self.revoke_inactive_or_disallowed(tenant)
        summary = entitlements.summary(tenant)
        active = set(summary.active_modules)
        plan = entitlements.get_company_plan(tenant)
        granted = self.granted_actions(tenant.company_id)
        modules = []
        for module_code in catalog_modules():
            module_active = module_code in active and plan.allows_module(module_code)
            actions = []
            for action_code in actions_for_module(module_code):
                is_granted = (module_code, action_code) in granted
                actions.append({
                    "action_code": action_code,
                    "granted": is_granted,
                    "locked": not module_active,
                    "tools": sorted(tools_for_action(module_code, action_code)),
                })
            modules.append({
                "module_code": module_code,
                "active": module_active,
                "locked": not module_active,
                "actions": actions,
            })
        language = "fr"
        if config is not None:
            language = voice_agent_language(self._session, config)
        return {
            "company_id": str(tenant.company_id),
            "agent_language": language,
            "permission_epoch": self.current_epoch(tenant.company_id),
            "default_grants": [],
            "modules": modules,
        }

    def _row(self, company_id: UUID, module_code: str, action_code: str) -> VoiceModulePermission | None:
        return self._session.scalar(
            select(VoiceModulePermission).where(
                VoiceModulePermission.company_id == company_id,
                VoiceModulePermission.module_code == module_code,
                VoiceModulePermission.action_code == action_code,
            )
        )

    def _revoke_row(self, row: VoiceModulePermission) -> None:
        now = datetime.now(timezone.utc)
        row.granted = False
        row.revoked_at = now
        row.permission_epoch = int(row.permission_epoch or 0) + 1


__all__ = [
    "VoiceModulePermissionError",
    "VoiceModulePermissionService",
]
