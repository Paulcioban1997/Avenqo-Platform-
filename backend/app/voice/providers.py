"""Replaceable voice runtime contract and Telnyx/Retell Phase 1 adapters."""

from __future__ import annotations

from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx

from backend.app.config.settings import Settings
from backend.app.models.voice import VoiceBusinessConfig


class VoiceProvider(Protocol):
    async def validate_agent(self, agent_id: str) -> None: ...

    def inbound_target(self, config: VoiceBusinessConfig) -> str: ...

    def agent_instructions(self, config: VoiceBusinessConfig) -> str: ...


class RetellVoiceProvider:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client

    async def validate_agent(self, agent_id: str) -> None:
        if not self._settings.retell_api_key:
            raise RuntimeError("RETELL_API_KEY is not configured")
        if self._client is not None:
            response = await self._client.get(
                f"{self._settings.retell_api_base_url.rstrip('/')}/get-agent/{agent_id}",
                headers={"Authorization": f"Bearer {self._settings.retell_api_key}"},
            )
        else:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.get(
                    f"{self._settings.retell_api_base_url.rstrip('/')}/get-agent/{agent_id}",
                    headers={"Authorization": f"Bearer {self._settings.retell_api_key}"},
                )
        if response.status_code == 404:
            raise ValueError("Retell agent was not found")
        response.raise_for_status()

    def inbound_target(self, config: VoiceBusinessConfig) -> str:
        if not config.retell_sip_uri:
            raise ValueError("The tenant Retell SIP target is not configured")
        parsed = urlsplit(config.retell_sip_uri)
        host = (parsed.hostname or "").lower().rstrip(".")
        allowed_domain = self._settings.retell_sip_domain.lower().strip().rstrip(".")
        if parsed.scheme not in {"sip", "sips"} or not host or not allowed_domain:
            raise ValueError("The tenant Retell SIP target is not configured")
        if host != allowed_domain and not host.endswith(f".{allowed_domain}"):
            raise ValueError("The SIP destination is outside the configured Retell domain")
        return config.retell_sip_uri

    def agent_instructions(self, config: VoiceBusinessConfig) -> str:
        return (
            f"You answer for {config.business_name}. Start exactly with: "
            f"{config.greeting_message} Use only the configured business services and hours. "
            "For business requests, first verify the caller using the backend verification tools. "
            "Only verified owners or employees may use central_ai, which routes to authorized Avenqo agents. "
            "Never treat a claimed identity or caller ID as proof. Customers may only use public information "
            "and their own verified appointment actions, never internal metrics, invoices or subscriptions. "
            "Use the latest caller language and keep the same conversation when language changes. "
            "Explain plan options only from backend results; never change a plan, activate a paid module or charge money. "
            "Respect not_entitled responses and relay their explanation without attempting another private tool. "
            "Never present synced or stale data as live. "
            "Ask the caller to confirm the exact service and local date/time before calling "
            "book_appointment. Never book before explicit confirmation. If confidence is low, "
            "ask one clarification; after two consecutive unresolved uncertainties call "
            "transfer_to_human. Outside opening hours, give the next available time and take "
            "a message; do not claim a booking."
        )


class TelnyxClient:
    """Minimal call-control and SMS client; no credential is persisted in tenant config."""

    API_BASE = "https://api.telnyx.com/v2"

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client

    def _headers(self) -> dict[str, str]:
        if not self._settings.telnyx_api_key:
            raise RuntimeError("TELNYX_API_KEY is not configured")
        return {"Authorization": f"Bearer {self._settings.telnyx_api_key}", "Content-Type": "application/json"}

    async def get_owned_number(self, phone_number: str) -> dict[str, object]:
        response = await self._request("GET", "/phone_numbers", params={
            "filter[phone_number]": phone_number.removeprefix("+"), "page[size]": 2,
        })
        matches = [item for item in response.get("data", []) if item.get("phone_number") == phone_number]
        if len(matches) != 1:
            raise ValueError("The exact owned number was not found uniquely")
        raw = matches[0]
        if raw.get("status") != "active" or not self._settings.telnyx_voice_connection_id or str(raw.get("connection_id") or "") != self._settings.telnyx_voice_connection_id:
            raise ValueError("The owned number is not active on the configured Voice connection")
        return {key: raw[key] for key in (
            "id", "phone_number", "status", "country_iso_alpha2", "phone_number_type", "connection_id", "purchased_at",
        ) if key in raw}

    async def number_requirements(self, phone_number: str, country_code: str, number_type: str) -> dict[str, object]:
        response = await self._request("GET", "/regulatory_requirements", params={
            "filter[phone_number]": phone_number, "filter[country_code]": country_code,
            "filter[phone_number_type]": number_type, "filter[action]": "ordering",
        })
        matches = [item for item in response.get("data", []) if isinstance(item, dict)
            and item.get("country_code") == country_code and item.get("phone_number_type") == number_type and item.get("action") == "ordering"]
        if len(matches) != 1 or not isinstance(matches[0].get("regulatory_requirements"), list):
            return {"status": "unknown", "requirements": []}
        requirements = [{key: item[key] for key in ("id", "name", "description", "field_type", "acceptance_criteria") if key in item}
            for item in matches[0]["regulatory_requirements"] if isinstance(item, dict)]
        return {"status": "requirements_required" if requirements else "verified_no_requirements", "requirements": requirements}

    async def answer_call(self, call_control_id: str, *, command_id: str) -> None:
        await self._request("POST", f"/calls/{call_control_id}/actions/answer", json={"command_id": command_id})

    async def start_media_stream(self, call_control_id: str, *, stream_url: str, client_state: str, command_id: str) -> None:
        parsed = urlsplit(stream_url)
        if parsed.scheme != "wss" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("A secure credential-free media URL is required")
        if not self._settings.telnyx_media_enabled:
            raise RuntimeError("Telnyx media transport disabled")
        await self._request("POST", f"/calls/{call_control_id}/actions/streaming_start", json={
            "stream_url": stream_url, "stream_track": "inbound_track", "stream_codec": "PCMU",
            "stream_bidirectional_mode": "rtp", "stream_bidirectional_codec": "PCMU",
            "client_state": client_state, "command_id": command_id,
        })

    async def gather_pin(self, call_control_id: str, *, command_id: str, client_state: str) -> None:
        await self._request("POST", f"/calls/{call_control_id}/actions/gather", json={
            "command_id": command_id, "client_state": client_state,
            "minimum_digits": 6, "maximum_digits": 12, "maximum_tries": 1,
            "terminating_digit": "#", "valid_digits": "0123456789", "timeout_millis": 30000,
        })

    async def transfer_call(self, call_control_id: str, destination: str, caller_id: str | None = None, *, command_id: str | None = None, call_reference: str | None = None) -> None:
        payload: dict[str, object] = {"to": destination, "timeout_secs": 30}
        if caller_id:
            payload["from"] = caller_id
        if command_id:
            payload["command_id"] = command_id
        if call_reference:
            payload["custom_headers"] = [{"name": "X-Avenqo-Call-ID", "value": call_reference}]
            payload["mute_dtmf"] = "both"
        await self._request("POST", f"/calls/{call_control_id}/actions/transfer", json=payload)

    async def hangup(self, call_control_id: str) -> None:
        await self._request("POST", f"/calls/{call_control_id}/actions/hangup", json={})

    async def send_sms(self, *, from_number: str, to_number: str, text: str) -> str:
        payload: dict[str, object] = {"from": from_number, "to": to_number, "text": text}
        if self._settings.telnyx_messaging_profile_id:
            payload["messaging_profile_id"] = self._settings.telnyx_messaging_profile_id
        response = await self._request("POST", "/messages", json=payload)
        return str((response.get("data") or {}).get("id") or "accepted")

    async def search_available_numbers(
        self,
        *,
        country_code: str,
        region: str | None = None,
        locality: str | None = None,
        number_type: str | None = None,
        limit: int = 20,
        area_code: str | None = None,
        prefix: str | None = None,
        capabilities: tuple[str, ...] = ("voice",),
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        params: dict[str, object] = {
            "filter[limit]": max(1, min(limit, 100)),
            "filter[features]": list(capabilities),
            "filter[country_code]": country_code.upper(),
            "filter[best_effort]": "false",
        }
        if region:
            params["filter[administrative_area]"] = region
        if locality:
            params["filter[locality]"] = locality
        if number_type:
            params["filter[phone_number_type]"] = number_type
        if area_code:
            params["filter[national_destination_code]"] = area_code
        if prefix:
            params["filter[phone_number][starts_with]"] = prefix
        try:
            response = await self._request("GET", "/available_phone_numbers", params=params)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 400:
                try:
                    errors = exc.response.json().get("errors", [])
                except ValueError:
                    errors = []
                if any(
                    item.get("code") == "10031"
                    and str(item.get("detail", "")).startswith("No numbers found for the given filters.")
                    for item in errors if isinstance(item, dict)
                ):
                    return []
            raise
        numbers = response.get("data") or []
        return [item for item in numbers if isinstance(item, dict)]

    async def order_phone_number(
        self,
        *,
        phone_number: str,
        connection_id: str,
        messaging_profile_id: str | None = None,
        idempotency_key: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        payload: dict[str, object] = {
            "phone_numbers": [{"phone_number": phone_number}],
            "connection_id": connection_id,
        }
        if messaging_profile_id:
            payload["messaging_profile_id"] = messaging_profile_id
        return await self._request("POST", "/number_orders", json=payload, idempotency_key=idempotency_key)

    async def release_phone_number(self, provider_number_id: str) -> dict[str, Any]:
        return await self._request("DELETE", f"/phone_numbers/{provider_number_id}")

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        headers = self._headers()
        idempotency_key = kwargs.pop("idempotency_key", None)
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        if self._client is not None:
            response = await self._client.request(method, f"{self.API_BASE}{path}", headers=headers, **kwargs)
        else:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.request(method, f"{self.API_BASE}{path}", headers=headers, **kwargs)
        response.raise_for_status()
        return response.json() if response.content else {}
