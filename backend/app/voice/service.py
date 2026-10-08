"""Tenant-isolated voice-agent configuration, booking and call finalization."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import re
import secrets
from time import perf_counter
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.config.settings import Settings
from backend.app.models import (
    Company,
    CRMActivity,
    CRMClient,
    CRMCommunication,
    CRMNote,
    CRMService as CRMServiceModel,
    CompanyMembership,
    User,
    UserRole,
    VoiceBusinessConfig,
    VoiceCall,
    VoicePhoneNumber,
    VoiceToolAction,
)
from backend.app.services.crm_service import CRMService
from backend.app.core.permissions import permissions_for
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from backend.app.services.retail_source_service import RetailSourceNotFound, RetailSourceService
from backend.app.voice.providers import RetellVoiceProvider, TelnyxClient, VoiceProvider
from backend.app.voice.messages import voice_greeting
from backend.app.voice.auth import VoiceCallerAuth, redact_voice_secrets
from backend.app.voice.messages import voice_auth_message
from backend.app.assistants.registry import build_default_assistant_registry, agent_entitlements
from backend.app.ai.tools.business.crm_tools import CreateAppointmentTool, UpdateAppointmentTool, CancelAppointmentTool
from shared.ai_engine.contracts import TenantContext

_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_tenant_async_locks: dict[UUID, asyncio.Lock] = {}
_tenant_lock_guard = asyncio.Lock()
_logger = logging.getLogger("avenqo.voice")


def _api_key_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def new_voice_api_key() -> str:
    return "avqv_" + secrets.token_urlsafe(36)


async def _tenant_lock(company_id: UUID) -> asyncio.Lock:
    async with _tenant_lock_guard:
        return _tenant_async_locks.setdefault(company_id, asyncio.Lock())


def voice_action_key(config_id: UUID, call_id: UUID, tool_name: str, action_id: str, actor_scope: str = "") -> str:
    payload = f"avenqo-voice-action:{config_id}:{call_id}:{tool_name}:{action_id}"
    return hashlib.sha256((payload + f":{actor_scope}" if actor_scope else payload).encode("utf-8")).hexdigest()


def resolve_voice_source_context(db: Session, tenant: TenantContext) -> dict[str, Any]:
    """Resolve selected sources from authenticated server identity, never call/browser fields."""
    if not hasattr(db, "scalars"):
        return {
            "state": "UNAVAILABLE",
            "selection": None,
            "sources": [],
            "resolved_at": datetime.now(timezone.utc).isoformat(),
        }
    context = RetailSourceService(db).context(tenant)
    if context["source_type"] == "all":
        selected = [
            source for source in context["sources"]
            if source.enabled and source.status.upper() == "READY"
        ]
    else:
        selected = [
            source for source in context["sources"]
            if source.source_type == context["source_type"]
            and str(source.source_id) == str(context["source_id"])
            and source.status.upper() == "READY"
        ]
    cfg = db.scalar(
        select(VoiceBusinessConfig).where(VoiceBusinessConfig.company_id == tenant.company_id)
    )
    business_info = None
    if cfg is not None:
        business_info = {
            "business_name": cfg.business_name,
            "opening_hours": cfg.opening_hours,
            "services": cfg.services,
            "timezone": cfg.timezone_name,
        }

    return {
        "state": context["state"] if selected else "SOURCE_UNAVAILABLE" if context["source_type"] else context["state"],
        "selection": context["source_type"],
        "sources": [
            {
                "source_id": str(source.source_id),
                "dataset_id": str(source.dataset_id) if source.dataset_id else None,
                "source_type": source.source_type,
                "provider": source.provider,
                "name": source.display_name,
                "last_updated_at": source.last_synchronized_at.isoformat() if source.last_synchronized_at else None,
            }
            for source in selected
        ],
        "business_profile": business_info,
        "resolved_at": datetime.now(timezone.utc).isoformat(),
    }


class VoiceOrchestrator:
    def __init__(
        self,
        db: Session,
        settings: Settings,
        provider: VoiceProvider | None = None,
        telnyx: TelnyxClient | None = None,
    ) -> None:
        self.db = db
        self.settings = settings
        self.provider = provider or RetellVoiceProvider(settings)
        self.telnyx = telnyx or TelnyxClient(settings)

    @staticmethod
    def greeting_for(business_name: str, locale: str = "fr") -> str:
        return voice_greeting(locale, business_name)

    def active_module(self, tenant: TenantContext) -> bool:
        return ModuleEntitlementService(self.db).can_use_module(tenant, "voice")

    def config_for_tenant(self, tenant: TenantContext) -> VoiceBusinessConfig | None:
        return self.db.scalar(
            select(VoiceBusinessConfig).where(VoiceBusinessConfig.company_id == tenant.company_id)
        )

    def ensure_config(
        self,
        tenant: TenantContext,
        phone_number: str | None = None,
    ) -> VoiceBusinessConfig:
        """Idempotently ensure a VoiceBusinessConfig exists for tenant and binds any active number."""
        config = self.config_for_tenant(tenant)
        company = self.db.scalar(select(Company).where(Company.id == tenant.company_id))

        active_number = self.db.scalar(
            select(VoicePhoneNumber).where(
                VoicePhoneNumber.company_id == tenant.company_id,
                VoicePhoneNumber.status == "ACTIVE",
            )
        )
        resolved_number = phone_number or (active_number.phone_number if active_number is not None else None)

        if config is None:
            api_key = new_voice_api_key()
            business_name = company.name if company is not None else "Avenqo Business"
            pref_lang = (company.preferred_language if company is not None else None) or "fr"
            timezone_name = (company.timezone if company is not None else None) or "America/Toronto"

            config = VoiceBusinessConfig(
                company_id=tenant.company_id,
                business_name=business_name,
                timezone_name=timezone_name,
                preferred_language=pref_lang,
                telnyx_phone_number=resolved_number,
                opening_hours={},
                services=[],
                greeting_message=self.greeting_for(business_name, pref_lang),
                voice_api_key_hash=_api_key_hash(api_key),
                voice_api_key_last4=api_key[-4:],
                enabled=False,
            )
            self.db.add(config)
            self.db.flush()
        else:
            if resolved_number and config.telnyx_phone_number != resolved_number:
                config.telnyx_phone_number = resolved_number
                self.db.flush()

        if active_number is not None and config.telnyx_phone_number == active_number.phone_number:
            if active_number.config_id != config.id:
                active_number.config_id = config.id
                self.db.flush()

        return config

    @staticmethod
    def public_config(config: VoiceBusinessConfig) -> dict[str, Any]:
        return {
            "id": config.id,
            "business_name": config.business_name,
            "timezone_name": config.timezone_name,
            "opening_hours": config.opening_hours,
            "services": config.services,
            "transfer_phone": config.transfer_phone,
            "telnyx_phone_number": config.telnyx_phone_number,
            "preferred_language": config.preferred_language,
            "greeting_message": config.greeting_message,
            "retell_agent_id": config.retell_agent_id,
            "retell_sip_uri": config.retell_sip_uri,
            "voice_api_key_last4": config.voice_api_key_last4,
            "enabled": config.enabled,
        }

    async def upsert_config(
        self,
        tenant: TenantContext,
        values: dict[str, Any],
        *,
        create_only: bool = False,
    ) -> tuple[VoiceBusinessConfig, str | None]:
        if not self.active_module(tenant):
            raise PermissionError("Le module Voice doit être activé pour cette entreprise.")
        try:
            ZoneInfo(values["timezone_name"])
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Fuseau horaire IANA inconnu") from exc
        agent_id = values.get("retell_agent_id")
        sip_uri = values.get("retell_sip_uri")
        if bool(agent_id) != bool(sip_uri) or values.get("enabled") and not agent_id:
            raise ValueError("A real conversation provider is required to enable inbound audio")
        if agent_id:
            await self.provider.validate_agent(agent_id)

        config = self.config_for_tenant(tenant)
        requested_number = values.get("telnyx_phone_number")
        number = None
        if requested_number:
            number = self.db.scalar(select(VoicePhoneNumber).where(
                VoicePhoneNumber.phone_number == requested_number
            ))
            if number is not None:
                if number.company_id != tenant.company_id:
                    raise PermissionError("This number belongs to another tenant.")
                if number.status != "ACTIVE":
                    raise ValueError("Only an active, provider-confirmed number can be assigned to Voice.")
                if number.config_id not in {None, config.id if config is not None else None}:
                    raise ValueError("This number is already assigned to another Voice configuration.")
            elif self.settings.telnyx_api_key:
                raise ValueError("Search and provision a tenant-owned Voice number before configuring inbound calls.")
        if config is not None and create_only:
            raise ValueError("La configuration Voice existe déjà; utilisez la mise à jour.")
        if config is None:
            api_key = new_voice_api_key()
            config = VoiceBusinessConfig(
                company_id=tenant.company_id,
                voice_api_key_hash=_api_key_hash(api_key),
                voice_api_key_last4=api_key[-4:],
                greeting_message=self.greeting_for(values["business_name"], values.get("preferred_language", "fr")),
                **values,
            )
            self.db.add(config)
            self.db.flush()
        else:
            previous_number = self.db.scalar(select(VoicePhoneNumber).where(
                VoicePhoneNumber.config_id == config.id
            ))
            if previous_number is not None and requested_number and previous_number.phone_number != requested_number:
                previous_number.config_id = None
            api_key = None
            for field, value in values.items():
                setattr(config, field, value)
        config.greeting_message = self.greeting_for(config.business_name, config.preferred_language)
        if agent_id:
            self.provider.inbound_target(config)
        if number is not None:
            number.config_id = config.id
        self.db.commit()
        self.db.refresh(config)
        return config, api_key

    def rotate_api_key(self, tenant: TenantContext) -> tuple[VoiceBusinessConfig, str]:
        config = self.config_for_tenant(tenant)
        if config is None:
            raise LookupError("Voice configuration not found")
        api_key = new_voice_api_key()
        config.voice_api_key_hash = _api_key_hash(api_key)
        config.voice_api_key_last4 = api_key[-4:]
        self.db.commit()
        self.db.refresh(config)
        return config, api_key

    def config_from_api_key(self, api_key: str | None) -> VoiceBusinessConfig | None:
        if not api_key or not api_key.startswith("avqv_"):
            return None
        return self.db.scalar(
            select(VoiceBusinessConfig).where(
                VoiceBusinessConfig.voice_api_key_hash == _api_key_hash(api_key),
                VoiceBusinessConfig.enabled.is_(True),
            )
        )

    def config_for_agent(self, agent_id: str) -> VoiceBusinessConfig | None:
        return self.db.scalar(
            select(VoiceBusinessConfig).where(
                VoiceBusinessConfig.retell_agent_id == agent_id,
                VoiceBusinessConfig.enabled.is_(True),
            )
        )

    def record_inbound(self, config: VoiceBusinessConfig, payload: dict[str, Any]) -> VoiceCall:
        control_id = str(payload.get("call_control_id") or "")
        if not control_id:
            raise ValueError("Telnyx event is missing call_control_id")
        existing = self.db.scalar(
            select(VoiceCall).where(VoiceCall.telnyx_call_control_id == control_id)
        )
        if existing:
            if existing.company_id != config.company_id or existing.config_id != config.id:
                raise PermissionError("Call is not owned by this tenant configuration")
            return existing
        now = datetime.now(timezone.utc)
        call = VoiceCall(
            company_id=config.company_id,
            config_id=config.id,
            telnyx_call_control_id=control_id,
            caller_phone=str(payload.get("from") or "unknown"),
            status="incoming",
            started_at=now,
        )
        self.db.add(call)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            existing = self.db.scalar(
                select(VoiceCall).where(VoiceCall.telnyx_call_control_id == control_id)
            )
            if existing is None:
                raise
            if existing.company_id != config.company_id or existing.config_id != config.id:
                raise PermissionError("Call is not owned by this tenant configuration")
            return existing
        self.db.refresh(call)
        return call

    def _resolve_call(
        self,
        config: VoiceBusinessConfig,
        call_id: str,
        caller_phone: str | None = None,
    ) -> VoiceCall:
        call = self.db.scalar(
            select(VoiceCall).where(
                VoiceCall.config_id == config.id,
                (VoiceCall.retell_call_id == call_id) | (VoiceCall.telnyx_call_control_id == call_id),
            )
        )
        if call:
            return call
        # Retell can issue function calls before its first call-status callback.
        unmatched_calls = list(self.db.scalars(
            select(VoiceCall)
            .where(
                VoiceCall.config_id == config.id,
                VoiceCall.retell_call_id.is_(None),
                VoiceCall.ended_at.is_(None),
            )
            .order_by(VoiceCall.created_at.desc())
            .limit(10)
        ).all())
        if caller_phone:
            call = next((item for item in unmatched_calls if item.caller_phone == caller_phone), None)
        else:
            call = unmatched_calls[0] if len(unmatched_calls) == 1 else None
        if call:
            call.retell_call_id = call_id
            self.db.flush()
            return call
        call = VoiceCall(
            company_id=config.company_id,
            config_id=config.id,
            retell_call_id=call_id,
            caller_phone=caller_phone or "unknown",
            status="in_progress",
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(call)
        self.db.flush()
        return call

    async def execute_tool(
        self,
        config: VoiceBusinessConfig,
        call_id: str,
        action_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        started_at = perf_counter()
        call = self._resolve_call(config, call_id)
        if call.ended_at is not None or call.status in {"ended", "failed", "rejected", "routing_outcome_unknown"}:
            return {"success": False, "error": "voice_call_not_active"}
        mutations = {"book_appointment": CreateAppointmentTool, "reschedule_appointment": UpdateAppointmentTool, "cancel_appointment": CancelAppointmentTool}
        actor_scope = ""
        if tool_name in mutations:
            if arguments.get("confirmed") is not True:
                return {"success": False, "confirmation_required": True}
            authenticated = VoiceCallerAuth(self.db, self.settings).valid_session(call)
            if authenticated is None:
                return {"success": False, "error": "caller_verification_required"}
            actor_scope = f"{authenticated.principal_id}:{authenticated.authenticated_at.isoformat()}"
            registry = build_default_assistant_registry()
            active = frozenset(ModuleEntitlementService(self.db).get_active_modules(TenantContext(config.company_id)))
            tool = mutations[tool_name](self.db)
            agent_unavailable = False
            for agent_id in tool.agent_ids:
                agent = registry.get(agent_id)
                if agent is None or not agent_entitlements(agent).issubset(active):
                    agent_unavailable = True
                    break
            if agent_unavailable:
                return {"success": False, "error": "agent_not_available"}
            if authenticated.caller_type != "CUSTOMER":
                membership = self.db.scalar(select(CompanyMembership).where(CompanyMembership.company_id == config.company_id,
                    CompanyMembership.user_id == authenticated.principal_id, CompanyMembership.is_active.is_(True)))
                if membership is None or "crm:appointments:write" not in permissions_for(membership.role):
                    return {"success": False, "error": "not_authorized"}
        scoped_action_id = voice_action_key(config.id, call.id, tool_name, action_id, actor_scope)
        lock = await _tenant_lock(config.company_id)
        async with lock:
            legacy = self.db.scalar(select(VoiceToolAction).where(
                VoiceToolAction.config_id == config.id, VoiceToolAction.action_id == action_id,
            ))
            if legacy is not None:
                return {"success": False, "error": "legacy_action_context_unavailable"}
            action_id = scoped_action_id
            if self.db.get_bind().dialect.name == "postgresql":
                self.db.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                    {"lock_key": f"voice_tool:{config.company_id}:{action_id}"},
                )
            existing_action = self.db.scalar(
                select(VoiceToolAction).where(
                    VoiceToolAction.config_id == config.id,
                    VoiceToolAction.action_id == action_id,
                )
            )
            if existing_action:
                _logger.info(
                    "voice_tool_result tenant_id=%s call_id=%s action_id=%s tool_name=%s success=%s replay=true latency_ms=%d",
                    config.company_id,
                    call.id,
                    action_id,
                    tool_name,
                    str(existing_action.result.get("success", False)).lower(),
                    int((perf_counter() - started_at) * 1000),
                )
                return existing_action.result

            action = VoiceToolAction(
                company_id=config.company_id,
                config_id=config.id,
                action_id=action_id,
                tool_name=tool_name,
                result={"status": "in_progress"},
            )
            self.db.add(action)
            self.db.commit()

            try:
                result = await self._dispatch_tool(
                    config,
                    call,
                    tool_name,
                    {**arguments, "_action_id": action_id},
                )
            except (ValueError, LookupError, PermissionError) as exc:
                result = {"success": False, "error": str(exc)}
            action = self.db.scalar(
                select(VoiceToolAction).where(
                    VoiceToolAction.config_id == config.id,
                    VoiceToolAction.action_id == action_id,
                )
            )
            if action:
                action.result = result
                self.db.commit()
            _logger.info(
                "voice_tool_result tenant_id=%s call_id=%s action_id=%s tool_name=%s success=%s replay=false latency_ms=%d",
                config.company_id,
                call.id,
                action_id,
                tool_name,
                str(result.get("success", False)).lower(),
                int((perf_counter() - started_at) * 1000),
            )
            return result

    async def _dispatch_tool(
        self,
        config: VoiceBusinessConfig,
        call: VoiceCall,
        tool_name: str,
        args: dict[str, Any],
    ) -> dict[str, Any]:
        if call.ended_at is not None or call.status in {"ended", "failed", "rejected"}:
            raise ValueError("L'appel est terminé; aucune action ne peut être exécutée.")
        if tool_name == "request_caller_verification":
            return await self._request_caller_verification(config, call)
        if tool_name == "request_pin_authentication":
            controller = VoiceCallerAuth(self.db, self.settings)
            if controller.valid_session(call) is not None:
                return {"success": True, "authenticated": True, "message": voice_auth_message(call.locale or config.preferred_language, 1)}
            call_control_id = call.telnyx_call_control_id
            if not call_control_id:
                return {"success": False, "error": "caller_authentication_unavailable", "message": voice_auth_message(call.locale or config.preferred_language, 2)}
            if call.verification_attempts >= getattr(self.settings, "voice_pin_max_attempts", 5):
                return {"success": False, "error": "caller_authentication_failed", "message": voice_auth_message(call.locale or config.preferred_language, 2)}
            client_state = controller.challenge(call)
            self.db.commit()
            try:
                await self.telnyx.gather_pin(call_control_id, command_id=str(UUID(args["_action_id"][:32])), client_state=client_state)
            except Exception:
                call.pin_challenge_hash = None; call.pin_challenge_expires_at = None; self.db.commit()
                return {"success": False, "error": "caller_authentication_unavailable", "message": voice_auth_message(call.locale or config.preferred_language, 2)}
            return {"success": True, "authentication_pending": True, "message": voice_auth_message(call.locale or config.preferred_language, 0)}
        if tool_name == "verify_caller":
            return self._verify_caller(config, call, str(args.get("code") or ""))
        if tool_name in {"reschedule_appointment", "cancel_appointment"}:
            if call.caller_type in {"OWNER", "EMPLOYEE"}:
                membership = self.db.scalar(select(CompanyMembership).where(
                    CompanyMembership.company_id == config.company_id,
                    CompanyMembership.user_id == call.authenticated_user_id,
                    CompanyMembership.is_active.is_(True),
                ))
                if membership is None or "crm:appointments:write" not in permissions_for(membership.role):
                    return {"success": False, "error": "not_authorized"}
            elif call.caller_type != "CLIENT" or call.verified_client_id is None:
                return {"success": False, "error": "caller_verification_required"}
        if tool_name == "get_business_info":
            return {
                "success": True,
                "business_name": config.business_name,
                "opening_hours": config.opening_hours,
                "services": config.services,
                "transfer_phone": config.transfer_phone,
                "timezone": config.timezone_name,
                "greeting_message": config.greeting_message,
            }
        if tool_name == "take_message":
            return self._take_message(config, call, args)
        if tool_name == "check_availability":
            return await self._check_availability(config, args)
        if tool_name == "book_appointment":
            return await self._book(config, call, args)
        if tool_name == "reschedule_appointment":
            return await self._reschedule(config, call, args)
        if tool_name == "cancel_appointment":
            return await self._cancel(config, call, args)
        if tool_name == "transfer_to_human":
            reason = str(args.get("reason") or "requested")
            if args.get("uncertain") is True:
                call.uncertainty_count += 1
                self.db.commit()
                if call.uncertainty_count < 2:
                    return {"success": True, "transfer": False, "action": "clarify_once", "uncertainty_count": 1}
            return await self._transfer(config, call, reason)
        raise ValueError("Outil vocal inconnu")

    @staticmethod
    def _normalized_phone(value: str | None) -> str | None:
        if not value:
            return None
        normalized = re.sub(r"[^0-9+]", "", value)
        return normalized if re.fullmatch(r"\+[1-9]\d{7,14}", normalized) else None

    def _verification_hash(self, config: VoiceBusinessConfig, call: VoiceCall, code: str) -> str:
        payload = f"{config.id}:{call.id}:{code}".encode("utf-8")
        return hmac.new(self.settings.auth_jwt_secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()

    async def _request_caller_verification(
        self,
        config: VoiceBusinessConfig,
        call: VoiceCall,
    ) -> dict[str, Any]:
        if VoiceCallerAuth(self.db, self.settings).valid_session(call) is not None:
            return {"success": True, "verified": True, "caller_type": call.caller_type}
        now = datetime.now(timezone.utc)
        expires = call.verification_expires_at
        if expires is not None and expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if call.verification_code_hash and expires and expires > now:
            return {"success": True, "verification_sent": True}

        caller_phone = self._normalized_phone(call.caller_phone)
        from_phone = config.telnyx_phone_number
        if caller_phone is None or not from_phone:
            return {"success": False, "error": "verification_unavailable"}
        matching_users = []
        users = self.db.scalars(select(User).where(
            User.company_id == config.company_id,
            User.is_active.is_(True),
        )).all()
        for user in users:
            if self._normalized_phone(user.phone) != caller_phone:
                continue
            membership = self.db.scalar(select(CompanyMembership).where(
                CompanyMembership.company_id == config.company_id,
                CompanyMembership.user_id == user.id,
                CompanyMembership.is_active.is_(True),
            ))
            if membership is not None:
                matching_users.append((user, membership))

        client = None
        if not matching_users:
            clients = self.db.scalars(select(CRMClient).where(
                CRMClient.company_id == config.company_id,
                CRMClient.is_deleted.is_(False),
            )).all()
            matching_clients = [item for item in clients if self._normalized_phone(item.phone) == caller_phone]
            client = matching_clients[0] if len(matching_clients) == 1 else None

        if len(matching_users) != 1 and client is None:
            return {"success": False, "error": "verification_unavailable"}
        code = f"{secrets.randbelow(1_000_000):06d}"
        call.verification_code_hash = self._verification_hash(config, call, code)
        call.verification_expires_at = now + timedelta(minutes=5)
        call.verification_attempts = 0
        call.verification_user_id = matching_users[0][0].id if matching_users else None
        call.verification_client_id = client.id if client is not None else None
        self.db.commit()
        message = (
            f"Code de vérification Avenqo : {code}. Il expire dans 5 minutes."
            if config.preferred_language.startswith("fr")
            else f"Your Avenqo verification code is {code}. It expires in 5 minutes."
        )
        try:
            await self.telnyx.send_sms(
                from_number=from_phone,
                to_number=caller_phone,
                text=message,
            )
        except Exception:
            call.verification_code_hash = None
            call.verification_expires_at = None
            call.verification_user_id = None
            call.verification_client_id = None
            self.db.commit()
            _logger.warning("Voice caller verification SMS delivery failed", extra={"company_id": str(config.company_id)})
            return {"success": False, "error": "verification_delivery_unavailable"}
        return {"success": True, "verification_sent": True}

    def _verify_caller(
        self,
        config: VoiceBusinessConfig,
        call: VoiceCall,
        code: str,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        expiry = call.verification_expires_at
        if expiry is not None and expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if not call.verification_code_hash or expiry is None or expiry <= now:
            return {"success": False, "error": "verification_expired"}
        call.verification_attempts += 1
        if call.verification_attempts > 5:
            call.verification_code_hash = None
            call.verification_user_id = None
            call.verification_client_id = None
            self.db.commit()
            return {"success": False, "error": "verification_attempts_exceeded"}
        candidate_hash = self._verification_hash(config, call, code)
        if not hmac.compare_digest(candidate_hash, call.verification_code_hash):
            self.db.commit()
            return {"success": False, "error": "verification_code_invalid"}

        if call.verification_user_id is not None:
            user = self.db.scalar(select(User).where(
                User.id == call.verification_user_id,
                User.company_id == config.company_id,
                User.is_active.is_(True),
            ))
            membership = self.db.scalar(select(CompanyMembership).where(
                CompanyMembership.company_id == config.company_id,
                CompanyMembership.user_id == call.verification_user_id,
                CompanyMembership.is_active.is_(True),
            ))
            if user is None or membership is None or self._normalized_phone(user.phone) != self._normalized_phone(call.caller_phone):
                return {"success": False, "error": "verification_identity_unavailable"}
            role = membership.role if isinstance(membership.role, UserRole) else UserRole(membership.role)
            call.authenticated_user_id = user.id
            call.caller_type = "OWNER" if role == UserRole.OWNER else "EMPLOYEE"
        elif call.verification_client_id is not None:
            client = self.db.scalar(select(CRMClient).where(
                CRMClient.id == call.verification_client_id,
                CRMClient.company_id == config.company_id,
                CRMClient.is_deleted.is_(False),
            ))
            if client is None or self._normalized_phone(client.phone) != self._normalized_phone(call.caller_phone):
                return {"success": False, "error": "verification_identity_unavailable"}
            call.verified_client_id = client.id
            call.caller_type = "CLIENT"
        else:
            return {"success": False, "error": "verification_identity_unavailable"}

        call.caller_verified_at = now
        call.verification_code_hash = None
        call.verification_expires_at = None
        call.verification_user_id = None
        call.verification_client_id = None
        VoiceCallerAuth(self.db, self.settings).establish(call)
        self.db.commit()
        return {"success": True, "verified": True, "caller_type": call.caller_type}

    def _service_config(self, config: VoiceBusinessConfig, service_name: str) -> dict[str, Any]:
        target = service_name.strip().casefold()
        service = next(
            (item for item in (config.services or []) if str(item.get("name", "")).strip().casefold() == target),
            None,
        )
        if not service:
            raise ValueError("Cette prestation n'est pas proposée par le commerce.")
        return service

    def _opening_interval(self, config: VoiceBusinessConfig, day: date) -> tuple[datetime, datetime] | None:
        windows = CRMService(self.db)._availability._windows(config.company_id, day)
        if not windows:
            return None
        return min(window[0] for window in windows), max(window[1] for window in windows)

    def _utc_datetime(self, value: Any, config: VoiceBusinessConfig) -> datetime:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return CRMService(self.db)._availability.normalize(config.company_id, parsed)

    async def _check_availability(self, config: VoiceBusinessConfig, args: dict[str, Any]) -> dict[str, Any]:
        service = self._service_config(config, str(args.get("service_name") or ""))
        day = date.fromisoformat(str(args["date"]))
        from backend.app.services.crm_availability_service import AvailabilityUnavailable
        try:
            interval = self._opening_interval(config, day)
        except AvailabilityUnavailable as exc:
            return {"success": False, "state": str(exc), "available_slots": [], "take_message": True}
        now = datetime.now(timezone.utc)
        if interval is None:
            suggestion = self._next_opening(config, day + timedelta(days=1))
            return {"success": True, "open": False, "available_slots": [], "next_opening": suggestion, "take_message": True}
        opening, closing = interval
        if now >= closing or day < now.astimezone(ZoneInfo(config.timezone_name)).date():
            suggestion = self._next_opening(config, day + timedelta(days=1))
            return {"success": True, "open": False, "available_slots": [], "next_opening": suggestion, "take_message": True}
        try:
            records = await CRMService(self.db)._availability.list_available_slots(
                config.company_id, day, duration_minutes=int(service["duration_minutes"]),
                service_id=UUID(str(service["crm_service_id"])) if service.get("crm_service_id") else None,
            )
        except AvailabilityUnavailable as exc:
            return {"success": False, "state": str(exc), "available_slots": [], "take_message": True}
        slots = [record["start_time"] for record in records]
        return {"success": True, "open": True, "available_slots": slots, "timezone": config.timezone_name}

    def _next_opening(self, config: VoiceBusinessConfig, from_day: date) -> str | None:
        for offset in range(14):
            day = from_day + timedelta(days=offset)
            interval = self._opening_interval(config, day)
            if interval and interval[0] > datetime.now(timezone.utc):
                return interval[0].astimezone(ZoneInfo(config.timezone_name)).isoformat()
        return None

    def _resolve_crm_service(self, config: VoiceBusinessConfig, service_data: dict[str, Any]) -> CRMServiceModel:
        supplied_id = service_data.get("crm_service_id")
        if supplied_id:
            service = self.db.scalar(
                select(CRMServiceModel).where(
                    CRMServiceModel.id == UUID(str(supplied_id)),
                    CRMServiceModel.company_id == config.company_id,
                    CRMServiceModel.is_active.is_(True),
                )
            )
            if not service:
                raise ValueError("La prestation CRM configurée est introuvable.")
            return service
        existing = self.db.scalar(
            select(CRMServiceModel).where(
                CRMServiceModel.company_id == config.company_id,
                CRMServiceModel.name.ilike(str(service_data["name"])),
                CRMServiceModel.is_active.is_(True),
            )
        )
        if existing:
            return existing
        service = CRMServiceModel(
            company_id=config.company_id,
            name=str(service_data["name"]),
            duration_minutes=int(service_data["duration_minutes"]),
            price=float(service_data.get("price", 0)),
            currency=str(service_data.get("currency", "CAD")),
            is_active=True,
        )
        self.db.add(service)
        self.db.flush()
        return service

    def _resolve_client(self, config: VoiceBusinessConfig, caller_name: str, caller_phone: str) -> CRMClient:
        phone = caller_phone.strip()
        client = self.db.scalar(
            select(CRMClient).where(
                CRMClient.company_id == config.company_id,
                CRMClient.phone == phone,
                CRMClient.is_deleted.is_(False),
            )
        )
        if client:
            return client
        parts = caller_name.strip().split(maxsplit=1)
        digest = hashlib.sha256(phone.encode()).hexdigest()[:24]
        return CRMService(self.db).create_client(
            config.company_id,
            {
                "first_name": parts[0],
                "last_name": parts[1] if len(parts) > 1 else "",
                "email": f"voice-{digest}@voice.invalid",
                "phone": phone,
                "industry_metadata": {"source": "inbound_voice"},
                "tags": ["voice-agent"],
            },
            actor_name="Avenqo Voice",
        )

    async def _book(self, config: VoiceBusinessConfig, call: VoiceCall, args: dict[str, Any]) -> dict[str, Any]:
        if args.get("confirmed") is not True:
            return {"success": False, "confirmation_required": True}
        service_cfg = self._service_config(config, str(args.get("service_name") or ""))
        start = self._utc_datetime(args["starts_at"], config)
        end = start + timedelta(minutes=int(service_cfg["duration_minutes"]))
        interval = self._opening_interval(config, start.astimezone(ZoneInfo(config.timezone_name)).date())
        if interval is None or start < interval[0] or end > interval[1]:
            return {"success": False, "outside_opening_hours": True, "take_message": True}
        crm_service = self._resolve_crm_service(config, service_cfg)
        if call.caller_type == "CLIENT":
            client = self.db.scalar(select(CRMClient).where(CRMClient.company_id == config.company_id,
                CRMClient.id == call.verified_client_id, CRMClient.is_deleted.is_(False)))
            if client is None or self._normalized_phone(str(args.get("caller_phone") or "")) != self._normalized_phone(client.phone):
                return {"success": False, "error": "customer_identity_mismatch"}
        else:
            client = self._resolve_client(config, str(args["caller_name"]), str(args["caller_phone"]))
        appointment, error = await CRMService(self.db).create_appointment(
            config.company_id,
            {
                "client_id": client.id,
                "service_id": crm_service.id,
                "title": crm_service.name,
                "start_time": start,
                "duration_minutes": crm_service.duration_minutes,
                "price": crm_service.price,
                "currency": crm_service.currency,
                "status": "confirmed",
                "notes": "Réservé via l'agent vocal Avenqo.",
                "idempotency_key": f"voice:{config.company_id}:{call.id}:{args.get('_action_id') or call.id}",
            },
            actor_name="Avenqo Voice",
        )
        if error or appointment is None:
            return {"success": False, "conflict": True, "message": error or "appointment_creation_failed"}
        call.appointment_id = appointment.id
        call.status = "appointment_booked"
        self.db.commit()
        return {
            "success": True,
            "appointment_id": str(appointment.id),
            "service_name": crm_service.name,
            "starts_at": appointment.start_time.isoformat(),
            "ends_at": appointment.end_time.isoformat(),
            "timezone": config.timezone_name,
        }

    async def _reschedule(self, config: VoiceBusinessConfig, call: VoiceCall, args: dict[str, Any]) -> dict[str, Any]:
        if args.get("confirmed") is not True:
            return {"success": False, "confirmation_required": True}
        appointment_id = UUID(str(args["appointment_id"]))
        appointment = self.db.scalar(select(CRMAppointmentModel).where(
            CRMAppointmentModel.id == appointment_id,
            CRMAppointmentModel.company_id == config.company_id,
            CRMAppointmentModel.is_deleted.is_(False),
        ))
        if not appointment:
            raise LookupError("Rendez-vous introuvable.")
        if call.caller_type == "CLIENT" and appointment.client_id != call.verified_client_id:
            return {"success": False, "error": "appointment_not_owned_by_verified_caller"}
        start = self._utc_datetime(args["starts_at"], config)
        end = start + timedelta(minutes=appointment.duration_minutes)
        interval = self._opening_interval(config, start.astimezone(ZoneInfo(config.timezone_name)).date())
        if interval is None or start < interval[0] or end > interval[1]:
            return {"success": False, "outside_opening_hours": True}
        updated, error = await CRMService(self.db).update_appointment(
            config.company_id, appointment_id, {"start_time": start, "duration_minutes": appointment.duration_minutes}, actor_name="Avenqo Voice"
        )
        if error or updated is None:
            return {"success": False, "conflict": True, "message": error or "appointment_update_failed"}
        call.appointment_id = updated.id
        self.db.commit()
        return {"success": True, "appointment_id": str(updated.id), "starts_at": updated.start_time.isoformat(), "ends_at": updated.end_time.isoformat()}

    async def _cancel(self, config: VoiceBusinessConfig, call: VoiceCall, args: dict[str, Any]) -> dict[str, Any]:
        if args.get("confirmed") is not True:
            return {"success": False, "confirmation_required": True}
        appointment_id = UUID(str(args["appointment_id"]))
        appointment = self.db.scalar(select(CRMAppointmentModel).where(
            CRMAppointmentModel.id == appointment_id,
            CRMAppointmentModel.company_id == config.company_id,
        ))
        if not appointment:
            raise LookupError("Rendez-vous introuvable.")
        if call.caller_type == "CLIENT" and appointment.client_id != call.verified_client_id:
            return {"success": False, "error": "appointment_not_owned_by_verified_caller"}
        if not await CRMService(self.db).cancel_appointment(config.company_id, appointment_id, actor_name="Avenqo Voice"):
            raise LookupError("Rendez-vous introuvable.")
        call.appointment_id = appointment_id
        call.status = "appointment_cancelled"
        self.db.commit()
        return {"success": True, "appointment_id": str(appointment_id), "status": "cancelled"}

    async def _transfer(self, config: VoiceBusinessConfig, call: VoiceCall, reason: str) -> dict[str, Any]:
        call_control_id = call.telnyx_call_control_id
        if not config.transfer_phone or not call_control_id:
            return {"success": False, "transfer": False, "message": "Aucun transfert humain n'est configuré."}
        await self.telnyx.transfer_call(call_control_id, config.transfer_phone, config.telnyx_phone_number)
        call.status = "transferred"
        self.db.commit()
        return {"success": True, "transfer": True, "reason": reason}

    def _take_message(self, config: VoiceBusinessConfig, call: VoiceCall, args: dict[str, Any]) -> dict[str, Any]:
        client = self._resolve_client(config, str(args["caller_name"]), str(args["caller_phone"]))
        message = str(args["message"]).strip()
        self.db.add(CRMNote(
            company_id=config.company_id,
            client_id=client.id,
            author_name="Avenqo Voice",
            content=f"Message téléphonique hors heures d'ouverture : {message}",
        ))
        self.db.add(CRMCommunication(
            company_id=config.company_id,
            client_id=client.id,
            channel="call",
            direction="inbound",
            subject="Message téléphonique",
            content=message,
            status="received",
            sent_at=datetime.now(timezone.utc),
        ))
        call.caller_phone = str(args["caller_phone"])
        call.summary = redact_voice_secrets(message)
        call.status = "message_taken"
        self.db.commit()
        return {"success": True, "message_recorded": True}

    async def finish_call(self, config: VoiceBusinessConfig, call_id: str, call_data: dict[str, Any]) -> VoiceCall:
        call = self._resolve_call(config, call_id)
        call.status = "ended"
        call.ended_at = datetime.now(timezone.utc)
        call.transcript = redact_voice_secrets(call_data.get("transcript")) or None
        analysis = call_data.get("call_analysis") or {}
        call.summary = redact_voice_secrets(analysis.get("call_summary") or call_data.get("summary")) or None
        activity_subject = f"Appel entrant Avenqo Voice {call.id}"
        activity = self.db.scalar(select(CRMActivity).where(
            CRMActivity.company_id == config.company_id,
            CRMActivity.activity_type == "call",
            CRMActivity.subject == activity_subject,
        ))
        activity_notes = "Résumé : " + (call.summary or "Aucun résumé fourni.")
        if call.transcript:
            activity_notes += "\n\nTranscription :\n" + call.transcript
        if activity is None:
            self.db.add(CRMActivity(
                company_id=config.company_id,
                activity_type="call",
                subject=activity_subject,
                status="completed",
                completed_at=call.ended_at,
                notes=activity_notes,
            ))
        else:
            activity.notes = activity_notes
            activity.completed_at = call.ended_at
        if call.appointment_id:
            appointment = self.db.get(CRMAppointmentModel, call.appointment_id)
            if appointment:
                existing_note = self.db.scalar(select(CRMNote).where(
                    CRMNote.company_id == config.company_id,
                    CRMNote.appointment_id == appointment.id,
                    CRMNote.author_name == "Avenqo Voice",
                ))
                content = "Résumé de l'appel : " + (call.summary or "Aucun résumé fourni.")
                if call.transcript:
                    content += "\n\nTranscription :\n" + call.transcript
                if existing_note:
                    existing_note.content = content
                else:
                    self.db.add(CRMNote(
                        company_id=config.company_id,
                        client_id=appointment.client_id,
                        appointment_id=appointment.id,
                        author_name="Avenqo Voice",
                        content=content,
                    ))
        self.db.commit()
        if call.appointment_id and call.sms_status != "sent":
            await self._send_confirmation(config, call)
        self.db.refresh(call)
        return call

    async def _send_confirmation(self, config: VoiceBusinessConfig, call: VoiceCall) -> None:
        from_number = config.telnyx_phone_number
        appointment = self.db.get(CRMAppointmentModel, call.appointment_id)
        if not appointment or call.caller_phone == "unknown" or not from_number:
            return
        local_time = appointment.start_time.astimezone(ZoneInfo(config.timezone_name)).strftime("%Y-%m-%d %H:%M")
        message = f"{config.business_name} : votre rendez-vous est confirmé le {local_time} ({config.timezone_name})."
        try:
            await self.telnyx.send_sms(from_number=from_number, to_number=call.caller_phone, text=message)
            call.sms_status = "sent"
            status_value = "sent"
        except Exception:
            call.sms_status = "failed"
            status_value = "failed"
        client = self.db.get(CRMClient, appointment.client_id)
        self.db.add(CRMCommunication(
            company_id=config.company_id,
            client_id=appointment.client_id,
            appointment_id=appointment.id,
            channel="sms",
            direction="outbound",
            subject="Confirmation de rendez-vous",
            content=message,
            status=status_value,
            sent_at=datetime.now(timezone.utc),
        ))
        self.db.commit()


# Kept local to avoid a broad public re-export change in the CRM package.
from backend.app.models.crm import CRMAppointment as CRMAppointmentModel


def ensure_voice_business_config(
    db: Session,
    company_id: UUID,
    phone_number: str | None = None,
) -> VoiceBusinessConfig:
    """Generic idempotent helper ensuring VoiceBusinessConfig exists for any company."""
    from backend.app.config.settings import get_settings
    settings = get_settings()
    orchestrator = VoiceOrchestrator(db, settings, RetellVoiceProvider(settings), TelnyxClient(settings))
    return orchestrator.ensure_config(TenantContext(company_id), phone_number)
