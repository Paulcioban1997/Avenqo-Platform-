"""Tenant-isolated voice-agent configuration, booking and call finalization."""

from __future__ import annotations

import asyncio
import hashlib
import secrets
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.config.settings import Settings
from backend.app.models import (
    CRMActivity,
    CRMClient,
    CRMCommunication,
    CRMNote,
    CRMService as CRMServiceModel,
    VoiceBusinessConfig,
    VoiceCall,
    VoiceToolAction,
)
from backend.app.services.crm_service import CRMService
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from backend.app.services.retail_source_service import RetailSourceNotFound
from backend.app.voice.providers import RetellVoiceProvider, TelnyxClient, VoiceProvider
from shared.ai_engine.contracts import TenantContext

_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_tenant_async_locks: dict[UUID, asyncio.Lock] = {}
_tenant_lock_guard = asyncio.Lock()


def _api_key_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def new_voice_api_key() -> str:
    return "avqv_" + secrets.token_urlsafe(36)


async def _tenant_lock(company_id: UUID) -> asyncio.Lock:
    async with _tenant_lock_guard:
        return _tenant_async_locks.setdefault(company_id, asyncio.Lock())


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
    def greeting_for(business_name: str) -> str:
        return f"Bonjour, {business_name.strip()}, assistant virtuel, cet appel peut être enregistré."

    def active_module(self, tenant: TenantContext) -> bool:
        return ModuleEntitlementService(self.db).can_use_module(tenant, "voice")

    def config_for_tenant(self, tenant: TenantContext) -> VoiceBusinessConfig | None:
        return self.db.scalar(
            select(VoiceBusinessConfig).where(VoiceBusinessConfig.company_id == tenant.company_id)
        )

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
        await self.provider.validate_agent(values["retell_agent_id"])

        config = self.config_for_tenant(tenant)
        if config is not None and create_only:
            raise ValueError("La configuration Voice existe déjà; utilisez la mise à jour.")
        if config is None:
            api_key = new_voice_api_key()
            config = VoiceBusinessConfig(
                company_id=tenant.company_id,
                voice_api_key_hash=_api_key_hash(api_key),
                voice_api_key_last4=api_key[-4:],
                **values,
            )
            self.db.add(config)
        else:
            api_key = None
            for field, value in values.items():
                setattr(config, field, value)
        config.greeting_message = self.greeting_for(config.business_name)
        self.provider.inbound_target(config)
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
        lock = await _tenant_lock(config.company_id)
        async with lock:
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
                return existing_action.result

            call = self._resolve_call(config, call_id)
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
        if tool_name == "get_business_info":
            return {
                "success": True,
                "business_name": config.business_name,
                "opening_hours": config.opening_hours,
                "services": config.services,
                "transfer_phone": config.transfer_phone,
                "timezone": config.timezone_name,
                "greeting_message": config.greeting_message,
                "instructions": self.provider.agent_instructions(config),
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
        local_zone = ZoneInfo(config.timezone_name)
        record = (config.opening_hours or {}).get(_WEEKDAYS[day.weekday()])
        if not isinstance(record, dict) or not record.get("open") or not record.get("close"):
            return None
        start_hour, start_minute = map(int, str(record["open"]).split(":"))
        end_hour, end_minute = map(int, str(record["close"]).split(":"))
        local_start = datetime.combine(day, time(start_hour, start_minute), tzinfo=local_zone)
        local_end = datetime.combine(day, time(end_hour, end_minute), tzinfo=local_zone)
        return local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc)

    @staticmethod
    def _utc_datetime(value: Any, config: VoiceBusinessConfig) -> datetime:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo(config.timezone_name))
        return parsed.astimezone(timezone.utc)

    async def _check_availability(self, config: VoiceBusinessConfig, args: dict[str, Any]) -> dict[str, Any]:
        service = self._service_config(config, str(args.get("service_name") or ""))
        day = date.fromisoformat(str(args["date"]))
        interval = self._opening_interval(config, day)
        now = datetime.now(timezone.utc)
        if interval is None:
            suggestion = self._next_opening(config, day + timedelta(days=1))
            return {"success": True, "open": False, "available_slots": [], "next_opening": suggestion, "take_message": True}
        opening, closing = interval
        if now >= closing or day < now.astimezone(ZoneInfo(config.timezone_name)).date():
            suggestion = self._next_opening(config, day + timedelta(days=1))
            return {"success": True, "open": False, "available_slots": [], "next_opening": suggestion, "take_message": True}
        from backend.app.services.crm_availability_service import AvailabilityUnavailable
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
        if error:
            return {"success": False, "conflict": True, "message": error}
        call.appointment_id = appointment.id
        call.caller_phone = str(args["caller_phone"])
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
        start = self._utc_datetime(args["starts_at"], config)
        end = start + timedelta(minutes=appointment.duration_minutes)
        interval = self._opening_interval(config, start.astimezone(ZoneInfo(config.timezone_name)).date())
        if interval is None or start < interval[0] or end > interval[1]:
            return {"success": False, "outside_opening_hours": True}
        updated, error = await CRMService(self.db).update_appointment(
            config.company_id, appointment_id, {"start_time": start, "duration_minutes": appointment.duration_minutes}, actor_name="Avenqo Voice"
        )
        if error:
            return {"success": False, "conflict": True, "message": error}
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
        if not await CRMService(self.db).cancel_appointment(config.company_id, appointment_id, actor_name="Avenqo Voice"):
            raise LookupError("Rendez-vous introuvable.")
        call.appointment_id = appointment_id
        call.status = "appointment_cancelled"
        self.db.commit()
        return {"success": True, "appointment_id": str(appointment_id), "status": "cancelled"}

    async def _transfer(self, config: VoiceBusinessConfig, call: VoiceCall, reason: str) -> dict[str, Any]:
        if not config.transfer_phone or not call.telnyx_call_control_id:
            return {"success": False, "transfer": False, "message": "Aucun transfert humain n'est configuré."}
        await self.telnyx.transfer_call(call.telnyx_call_control_id, config.transfer_phone, config.telnyx_phone_number)
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
        call.summary = message
        call.status = "message_taken"
        self.db.commit()
        return {"success": True, "message_recorded": True}

    async def finish_call(self, config: VoiceBusinessConfig, call_id: str, call_data: dict[str, Any]) -> VoiceCall:
        call = self._resolve_call(config, call_id)
        call.status = "ended"
        call.ended_at = datetime.now(timezone.utc)
        call.transcript = str(call_data.get("transcript") or "") or None
        analysis = call_data.get("call_analysis") or {}
        call.summary = str(analysis.get("call_summary") or call_data.get("summary") or "") or None
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
        appointment = self.db.get(CRMAppointmentModel, call.appointment_id)
        if not appointment or call.caller_phone == "unknown":
            return
        local_time = appointment.start_time.astimezone(ZoneInfo(config.timezone_name)).strftime("%Y-%m-%d %H:%M")
        message = f"{config.business_name} : votre rendez-vous est confirmé le {local_time} ({config.timezone_name})."
        try:
            await self.telnyx.send_sms(from_number=config.telnyx_phone_number, to_number=call.caller_phone, text=message)
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
