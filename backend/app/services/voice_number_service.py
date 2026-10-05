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


class VoiceNumberManagementService:
    """Provider-neutral international number search/provisioning boundary."""

    def __init__(self, provider: TelecomProvider) -> None:
        self._provider = provider

    async def search(self, request: PhoneNumberSearch) -> dict[str, Any]:
        country_code = request.country_code.upper()
        if not _COUNTRY_CODE.fullmatch(country_code):
            raise ValueError("country_code must be a two-letter ISO country code")
        if request.number_type not in {None, "local", "mobile", "toll_free", "national"}:
            raise ValueError("Unsupported international phone number type")
        raw_numbers = await self._provider.search_available_numbers(
            country_code=country_code,
            region=request.region,
            locality=request.locality,
            number_type=request.number_type,
            limit=max(1, min(request.limit, 100)),
        )
        offers = [self._offer(country_code, item) for item in raw_numbers]
        return {
            "status": "READY_FOR_OWNER_ACTION" if offers else "NO_NUMBERS_AVAILABLE",
            "country_code": country_code,
            "offers": offers,
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
        if not re.fullmatch(r"\+[1-9]\d{7,14}", phone_number):
            return {}
        features = {str(value).casefold() for value in (raw.get("features") or [])}
        cost_info = raw.get("cost_information") if isinstance(raw.get("cost_information"), dict) else {}
        monthly_cost = cost_info.get("monthly_cost")
        try:
            monthly_cost = float(monthly_cost) if monthly_cost is not None else None
        except (TypeError, ValueError):
            monthly_cost = None
        locations = raw.get("region_information") or []
        location = locations[0] if isinstance(locations, list) and locations and isinstance(locations[0], dict) else {}
        requirements = raw.get("regulatory_requirements") or raw.get("requirements") or []
        return {
            "phone_number": phone_number,
            "country_code": country_code,
            "region": location.get("region") or location.get("administrative_area"),
            "locality": location.get("locality"),
            "provider": "telnyx",
            "provider_number_id": raw.get("id"),
            "number_type": raw.get("phone_number_type") or "unknown",
            "voice_capability": "voice" in features,
            "sms_capability": "sms" in features,
            "monthly_cost": monthly_cost,
            "monthly_cost_currency": cost_info.get("currency") if monthly_cost is not None else None,
            "regulatory_status": "requirements_required" if requirements else "unknown",
            "regulatory_requirements": requirements,
            "status": "AVAILABLE",
            "provisioning_state": "READY_FOR_OWNER_ACTION",
        }