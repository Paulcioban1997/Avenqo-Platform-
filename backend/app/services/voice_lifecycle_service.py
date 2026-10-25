"""Voice agent lifecycle state machine and activation gatekeeper.

Enforces fail-closed multi-tenant voice lifecycle:
DRAFT -> CONFIGURING -> READY_FOR_TEST -> ACTIVE -> SUSPENDED

Rules:
- A reserved number does NOT authorize voice answering.
- Only ACTIVE numbers can answer public calls.
- READY_FOR_TEST numbers only answer registered tenant admin/owner test calls.
- Non-active numbers never open an OpenAI Realtime session or access company data.
- State changes require tenant admin confirmation and generate immutable audit logs.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.audit_log import AuditLogEntry
from backend.app.models.billing import BillingAccount
from backend.app.models.company import Company
from backend.app.models.user import User, UserRole
from backend.app.models.voice import VoiceBusinessConfig, VoicePhoneNumber
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from shared.ai_engine.contracts import TenantContext

logger = logging.getLogger("avenqo.voice.lifecycle")


class VoiceLifecycleStatus(str, Enum):
    DRAFT = "DRAFT"
    CONFIGURING = "CONFIGURING"
    READY_FOR_TEST = "READY_FOR_TEST"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


class VoiceLifecycleService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_status(self, company_id: UUID) -> dict[str, Any]:
        """Calculates the current lifecycle status and validation checklist."""
        config = self.db.scalar(
            select(VoiceBusinessConfig).where(VoiceBusinessConfig.company_id == company_id)
        )
        number = self.db.scalar(
            select(VoicePhoneNumber).where(
                VoicePhoneNumber.company_id == company_id,
                VoicePhoneNumber.provider == "telnyx",
            )
        )
        company = self.db.get(Company, company_id)
        account = self.db.scalar(
            select(BillingAccount).where(BillingAccount.company_id == company_id)
        )

        has_voice_module = bool(
            account
            and account.status.strip().lower() in {"active", "trialing"}
            and (
                ModuleEntitlementService(self.db).can_use_module(TenantContext(company_id), "voice")
                or (account.plan_code and account.plan_code.lower() in {"professional", "enterprise", "custom_enterprise"})
            )
        )

        call_policy = (config.call_policy or {}) if config else {}
        stored_status = call_policy.get("lifecycle_status")

        # Determine checklist
        phone_verified = bool(
            number
            and number.phone_number
            and config
            and config.telnyx_phone_number == number.phone_number
            and "voice" in (number.capabilities or [])
        )
        config_saved = bool(
            config
            and config.business_name
            and config.greeting_message
        )
        identity_defined = bool(
            company
            and company.name
            and company.industry
        )
        voice_selected = bool(
            config
            and config.voice_id
            and config.preferred_language
        )
        ivr_configured = bool(
            call_policy.get("ivr_enabled") is not None
        )
        ivr_enabled = bool(call_policy.get("ivr_enabled", True))
        ivr_greeting = call_policy.get(
            "ivr_greeting",
            f"Bienvenue chez {config.business_name if config else 'notre entreprise'}. Pour les employés, composez le 1. Pour le service clientèle, composez le 2.",
        )

        can_activate = (
            has_voice_module
            and phone_verified
            and config_saved
            and identity_defined
            and voice_selected
        )

        # Derive computed status if not explicitly set
        if not stored_status:
            if config and config.enabled:
                current_status = VoiceLifecycleStatus.ACTIVE.value
            elif can_activate:
                current_status = VoiceLifecycleStatus.READY_FOR_TEST.value
            elif config_saved or phone_verified:
                current_status = VoiceLifecycleStatus.CONFIGURING.value
            else:
                current_status = VoiceLifecycleStatus.DRAFT.value
        else:
            current_status = stored_status

        return {
            "status": current_status,
            "can_activate": can_activate,
            "checklist": {
                "subscription_active": has_voice_module,
                "phone_number_verified": phone_verified,
                "configuration_saved": config_saved,
                "identity_defined": identity_defined,
                "voice_and_language_selected": voice_selected,
                "ivr_configured": ivr_configured,
            },
            "phone_number": number.phone_number if number else None,
            "number_status": number.status if number else None,
            "ivr": {
                "enabled": ivr_enabled,
                "greeting": ivr_greeting,
                "employee_prompt": "Pour les employés, composez le 1 suivi de votre NIP personnel.",
                "customer_prompt": "Pour le service clientèle, composez le 2.",
            },
            "enabled": current_status == VoiceLifecycleStatus.ACTIVE.value,
        }

    def activate(self, company_id: UUID, actor_id: UUID) -> dict[str, Any]:
        """Activates a tenant voice agent after validating all prerequisites."""
        status_info = self.get_status(company_id)
        if not status_info["can_activate"]:
            missing = [k for k, v in status_info["checklist"].items() if not v]
            raise ValueError(f"Activation conditions not met. Missing prerequisites: {', '.join(missing)}")

        config = self.db.scalar(
            select(VoiceBusinessConfig).where(VoiceBusinessConfig.company_id == company_id)
        )
        if not config:
            raise ValueError("Voice configuration record not found.")

        number = self.db.scalar(
            select(VoicePhoneNumber).where(
                VoicePhoneNumber.company_id == company_id,
                VoicePhoneNumber.phone_number == config.telnyx_phone_number,
            )
        )

        policy = dict(config.call_policy or {})
        policy["lifecycle_status"] = VoiceLifecycleStatus.ACTIVE.value
        policy["activated_at"] = datetime.now(timezone.utc).isoformat()
        policy["activated_by"] = str(actor_id)
        config.call_policy = policy
        config.enabled = True

        if number:
            number.status = "ACTIVE"

        # Audit log
        self._record_audit(
            company_id=company_id,
            actor_id=actor_id,
            action="voice.lifecycle.activate",
            details={
                "phone_number": config.telnyx_phone_number,
                "status": VoiceLifecycleStatus.ACTIVE.value,
            },
        )
        self.db.commit()

        logger.info(
            "Voice lifecycle activated company_id=%s phone=%s by actor=%s",
            company_id,
            config.telnyx_phone_number,
            actor_id,
        )
        return self.get_status(company_id)

    def suspend(self, company_id: UUID, actor_id: UUID, reason: str = "Admin suspended") -> dict[str, Any]:
        """Suspends a tenant voice agent, immediately blocking inbound sessions."""
        config = self.db.scalar(
            select(VoiceBusinessConfig).where(VoiceBusinessConfig.company_id == company_id)
        )
        if not config:
            raise ValueError("Voice configuration record not found.")

        number = self.db.scalar(
            select(VoicePhoneNumber).where(
                VoicePhoneNumber.company_id == company_id,
                VoicePhoneNumber.phone_number == config.telnyx_phone_number,
            )
        )

        policy = dict(config.call_policy or {})
        policy["lifecycle_status"] = VoiceLifecycleStatus.SUSPENDED.value
        policy["suspended_at"] = datetime.now(timezone.utc).isoformat()
        policy["suspended_by"] = str(actor_id)
        policy["suspension_reason"] = reason
        config.call_policy = policy
        config.enabled = False

        if number:
            number.status = "SUSPENDED"

        # Revoke active voice auth sessions
        from backend.app.models.voice import VoiceAuthSession
        now = datetime.now(timezone.utc)
        for s in self.db.scalars(
            select(VoiceAuthSession).where(
                VoiceAuthSession.company_id == company_id,
                VoiceAuthSession.revoked_at.is_(None),
            )
        ):
            s.revoked_at = now

        self._record_audit(
            company_id=company_id,
            actor_id=actor_id,
            action="voice.lifecycle.suspend",
            details={
                "phone_number": config.telnyx_phone_number,
                "status": VoiceLifecycleStatus.SUSPENDED.value,
                "reason": reason,
            },
        )
        self.db.commit()

        logger.info(
            "Voice lifecycle suspended company_id=%s phone=%s reason=%s by actor=%s",
            company_id,
            config.telnyx_phone_number,
            reason,
            actor_id,
        )
        return self.get_status(company_id)

    def update_ivr_settings(
        self,
        company_id: UUID,
        actor_id: UUID,
        *,
        ivr_enabled: bool,
        ivr_greeting: str | None = None,
    ) -> dict[str, Any]:
        """Updates IVR routing configuration for the tenant."""
        config = self.db.scalar(
            select(VoiceBusinessConfig).where(VoiceBusinessConfig.company_id == company_id)
        )
        if not config:
            raise ValueError("Voice configuration record not found.")

        policy = dict(config.call_policy or {})
        policy["ivr_enabled"] = ivr_enabled
        if ivr_greeting is not None:
            policy["ivr_greeting"] = ivr_greeting
        config.call_policy = policy

        self._record_audit(
            company_id=company_id,
            actor_id=actor_id,
            action="voice.ivr.update",
            details={
                "ivr_enabled": ivr_enabled,
                "ivr_greeting": ivr_greeting,
            },
        )
        self.db.commit()
        return self.get_status(company_id)

    def is_call_admissible(
        self,
        company_id: UUID,
        caller_phone: str,
    ) -> tuple[bool, str]:
        """Fail-closed admission test for an incoming telephone call.

        Returns (admitted: bool, reason: str).
        """
        status_info = self.get_status(company_id)
        current_status = status_info["status"]

        if current_status == VoiceLifecycleStatus.ACTIVE.value:
            return True, "ACTIVE"

        if current_status == VoiceLifecycleStatus.READY_FOR_TEST.value:
            # Check if caller is registered tenant owner/admin for testing
            user = self.db.scalar(
                select(User).where(
                    User.company_id == company_id,
                    User.phone == caller_phone,
                    User.is_active.is_(True),
                )
            )
            if user and user.role in {UserRole.OWNER, UserRole.ADMIN}:
                return True, "ADMIN_TEST_CALL"
            return False, "NOT_ACTIVE_PUBLIC_BLOCKED"

        if current_status == VoiceLifecycleStatus.SUSPENDED.value:
            return False, "SUSPENDED"

        return False, "CONFIGURING"

    def _record_audit(
        self,
        company_id: UUID,
        actor_id: UUID,
        action: str,
        details: dict[str, Any],
    ) -> None:
        try:
            entry = AuditLogEntry(
                id=uuid4(),
                actor_user_id=actor_id,
                company_id=company_id,
                action=action,
                target_type="voice_agent",
                target_id=str(company_id),
                safe_metadata=details,
                created_at=datetime.now(timezone.utc),
            )
            self.db.add(entry)
        except Exception as exc:
            logger.warning("Failed to record lifecycle audit log: %s", exc)
