from __future__ import annotations

import re
from datetime import datetime
from dataclasses import dataclass
from typing import Any, Protocol
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.app.core.permissions import permissions_for
from backend.app.models import BillingAccount, CompanyMembership, User, VoiceBusinessConfig, VoicePhoneNumber
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from shared.ai_engine.contracts import TenantContext

_COUNTRY_CODE = re.compile(r"^[A-Z]{2}$")


class TelecomProvider(Protocol):
    async def get_owned_number(self, phone_number: str) -> dict[str, object]: ...
    async def search_available_numbers(self, **kwargs) -> list[dict[str, object]]: ...

    async def order_phone_number(self, **kwargs) -> dict[str, object]: ...

    async def release_phone_number(self, provider_number_id: str) -> dict[str, object]: ...


class VoiceNumberOwnerActionRequired(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PhoneNumberSearch:
    country_code: str
    region: str | None = None
    locality: str | None = None
    number_type: str | None = None
    limit: int = 20
    area_code: str | None = None
    prefix: str | None = None
    capabilities: tuple[str, ...] = ("voice",)
    offset: int = 0


class VoiceNumberManagementService:
    """Provider-neutral international number search/provisioning boundary."""

    def __init__(self, provider: TelecomProvider) -> None:
        self._provider = provider

    async def register_owned_number(
        self, session: Session, tenant: TenantContext, phone_number: str, *, confirmed: bool,
    ) -> VoicePhoneNumber:
        if not confirmed or not re.fullmatch(r"\+[1-9]\d{7,14}", phone_number):
            raise ValueError("Explicit confirmation and an E.164 number are required")
        membership = session.scalar(select(CompanyMembership).where(
            CompanyMembership.company_id == tenant.company_id, CompanyMembership.user_id == tenant.user_id,
            CompanyMembership.is_active.is_(True),
        ))
        user = session.scalar(select(User).where(User.id == tenant.user_id,
            User.company_id == tenant.company_id, User.is_active.is_(True)))
        if membership is None or user is None or "modules:manage" not in permissions_for(membership.role):
            raise PermissionError("Active tenant membership and module management permission are required")
        account = session.scalar(select(BillingAccount).where(BillingAccount.company_id == tenant.company_id))
        if account is None or account.status.strip().lower() not in {"active", "trialing"}:
            raise PermissionError("An active subscription is required")
        if not ModuleEntitlementService(session).can_use_module(tenant, "voice"):
            raise PermissionError("Voice module must be active")
        record = await self._provider.get_owned_number(phone_number)
        if record.get("phone_number") != phone_number or record.get("status") != "active" or not record.get("id"):
            raise ValueError("An active provider-owned number is required")
        country = str(record.get("country_iso_alpha2") or "").upper()
        number_type = str(record.get("phone_number_type") or "")
        if not _COUNTRY_CODE.fullmatch(country) or not number_type or not record.get("connection_id"):
            raise ValueError("Provider number country, type and Voice connection are required")
        if session.get_bind().dialect.name == "postgresql":
            session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"), {"lock_key": f"voice_number:{phone_number}"})
        existing = session.scalar(select(VoicePhoneNumber).where(VoicePhoneNumber.phone_number == phone_number))
        configs = session.scalars(select(VoiceBusinessConfig).where(VoiceBusinessConfig.telnyx_phone_number == phone_number)).all()
        if any(item.company_id != tenant.company_id for item in configs) or existing is not None and existing.company_id != tenant.company_id:
            raise PermissionError("This number is already bound to another tenant")
        config = session.scalar(select(VoiceBusinessConfig).where(VoiceBusinessConfig.company_id == tenant.company_id))
        if config is not None and config.telnyx_phone_number != phone_number:
            raise ValueError("Existing Voice configuration uses a different number")
        if existing is not None:
            if existing.provider != "telnyx" or existing.status != "ACTIVE" or existing.provider_number_id != str(record["id"]):
                raise ValueError("Existing number lifecycle requires owner reconciliation")
            if existing.config_id not in {None, config.id if config is not None else None}:
                raise PermissionError("Number configuration binding does not match tenant")
            if config is not None:
                existing.config_id = config.id
            session.flush()
            return existing
        purchased_at = record.get("purchased_at")
        number = VoicePhoneNumber(
            company_id=tenant.company_id, config_id=config.id if config is not None else None,
            phone_number=phone_number, country_code=country, number_type=number_type, provider="telnyx",
            provider_number_id=str(record["id"]), status="ACTIVE", capabilities=["voice"],
            provider_connection_id=str(record["connection_id"]),
            regulatory_status="unknown", regulatory_requirements=[],
            purchased_at=datetime.fromisoformat(str(purchased_at).replace("Z", "+00:00")) if purchased_at else None,
        )
        session.add(number)
        session.flush()
        return number

    async def search(self, request: PhoneNumberSearch) -> dict[str, Any]:
        country_code = request.country_code.upper()
        if not _COUNTRY_CODE.fullmatch(country_code):
            raise ValueError("country_code must be a two-letter ISO country code")
        if request.number_type not in {None, "local", "mobile", "toll_free", "national", "shared_cost"}:
            raise ValueError("Unsupported international phone number type")
        if not 1 <= request.limit <= 100 or not 0 <= request.offset < 100 or request.offset + request.limit > 100:
            raise ValueError("Search window must be within 100 results")
        for value in (request.area_code, request.prefix):
            if value is not None and not re.fullmatch(r"\d{1,15}", value):
                raise ValueError("Area code and prefix must contain digits only")
        if not set(request.capabilities) <= {"voice", "sms", "mms", "fax", "emergency", "hd_voice", "international_sms", "local_calling"}:
            raise ValueError("Unsupported number capability")
        raw_numbers = await self._provider.search_available_numbers(
            country_code=country_code,
            region=request.region,
            locality=request.locality,
            number_type=request.number_type,
            limit=request.offset + request.limit,
            area_code=request.area_code,
            prefix=request.prefix,
            capabilities=request.capabilities,
        )
        offers = [offer for item in raw_numbers[request.offset:request.offset + request.limit] if (offer := self._offer(country_code, item))]
        return {
            "status": "READY_FOR_OWNER_ACTION" if offers else "NO_NUMBERS_AVAILABLE",
            "country_code": country_code,
            "offers": offers,
            "pagination": {
                "offset": request.offset,
                "limit": request.limit,
                "returned": len(offers),
                "mode": "bounded_inventory_window",
                "provider_pagination_supported": False,
                "total_available": None,
            },
        }

    async def provision(
        self,
        *,
        offer: dict[str, Any],
        confirmed: bool,
        connection_id: str | None,
        messaging_profile_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        if not confirmed:
            return {"status": "READY_FOR_OWNER_ACTION", "reason": "explicit_purchase_confirmation_required"}
        if not connection_id:
            raise VoiceNumberOwnerActionRequired("Configure a Telnyx Call Control connection before purchasing a number.")
        phone_number = str(offer.get("phone_number") or "")
        if not re.fullmatch(r"\+[1-9]\d{7,14}", phone_number) or offer.get("is_orderable") is False:
            raise ValueError("A provider-verified E.164 number offer is required")
        order = {
            "phone_number": phone_number,
            "connection_id": connection_id,
            "messaging_profile_id": messaging_profile_id,
        }
        if idempotency_key is not None:
            order["idempotency_key"] = idempotency_key
        return await self._provider.order_phone_number(**order)

    async def release(
        self,
        *,
        provider_number_id: str,
        confirmed: bool,
    ) -> dict[str, Any]:
        if not confirmed:
            return {"status": "READY_FOR_OWNER_ACTION", "reason": "explicit_release_confirmation_required"}
        if not provider_number_id.strip():
            raise ValueError("A tenant-owned provider number id is required")
        return await self._provider.release_phone_number(provider_number_id)

    @staticmethod
    def _offer(country_code: str, raw: dict[str, object]) -> dict[str, Any]:
        phone_number = str(raw.get("phone_number") or raw.get("number") or "")
        orderable = bool(re.fullmatch(r"\+[1-9]\d{7,14}", phone_number))
        if not orderable and not re.fullmatch(r"\+[1-9]\d*-+", phone_number):
            return {}
        features = {
            str(value.get("name", "") if isinstance(value, dict) else value).casefold()
            for value in (raw.get("features") or [])
        }
        cost_info = raw.get("cost_information") if isinstance(raw.get("cost_information"), dict) else {}
        monthly_cost = cost_info.get("monthly_cost")
        try:
            monthly_cost = float(monthly_cost) if monthly_cost is not None else None
        except (TypeError, ValueError):
            monthly_cost = None
        locations = raw.get("region_information") or []
        location = locations[0] if isinstance(locations, list) and locations and isinstance(locations[0], dict) else {}
        regions = {item.get("region_type"): item.get("region_name") for item in locations if isinstance(item, dict)}
        requirements = raw.get("regulatory_requirements") or raw.get("requirements") or []
        return {
            "phone_number": phone_number,
            "country_code": regions.get("country_code") or raw.get("country_code"),
            "region": regions.get("state") or location.get("region") or location.get("administrative_area"),
            "locality": regions.get("location") or location.get("locality"),
            "region_information": locations,
            "provider": "telnyx",
            "provider_number_id": raw.get("id"),
            "number_type": raw.get("phone_number_type") or "unknown",
            "voice_capability": "voice" in features if "features" in raw else None,
            "sms_capability": "sms" in features if "features" in raw else None,
            "mms_capability": "mms" in features if "features" in raw else None,
            "capabilities": sorted(features),
            "cost_information": {key: cost_info[key] for key in ("monthly_cost", "upfront_cost", "currency") if key in cost_info},
            "monthly_cost": monthly_cost,
            "monthly_cost_currency": cost_info.get("currency") if monthly_cost is not None else None,
            "regulatory_status": "requirements_required" if requirements else "unknown",
            "regulatory_requirements": requirements,
            "status": "AVAILABLE",
            "provisioning_state": "READY_FOR_OWNER_ACTION",
            "is_orderable": orderable,
        }