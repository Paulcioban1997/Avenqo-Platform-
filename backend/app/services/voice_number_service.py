from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol

_COUNTRY_CODE = re.compile(r"^[A-Z]{2}$")


class TelecomProvider(Protocol):
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
        if not phone_number.startswith("+") or not offer.get("provider_number_id"):
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