"""Microsoft Outlook / Graph Calendar provider architecture placeholder for Avenqo CRM AI."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from backend.app.services.calendar.base import (
    BusySlot,
    CalendarEventData,
    CalendarProvider,
    CalendarProviderError,
)


class OutlookCalendarProvider(CalendarProvider):
    """Outlook / Microsoft 365 Calendar provider using Microsoft Graph API."""

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        redirect_uri: str | None = None,
    ) -> None:
        self._client_id = client_id or ""
        self._client_secret = client_secret or ""
        self._redirect_uri = redirect_uri or ""

    @property
    def provider_name(self) -> str:
        return "outlook"

    def get_auth_url(self, state: str, redirect_uri: str | None = None) -> str:
        tenant = "common"
        endpoint = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"
        scopes = "Calendars.ReadWrite User.Read offline_access"
        eff_redirect = redirect_uri or self._redirect_uri
        return (
            f"{endpoint}?client_id={self._client_id}"
            f"&response_type=code"
            f"&redirect_uri={eff_redirect}"
            f"&scope={scopes}"
            f"&state={state}"
        )

    async def exchange_code(self, code: str, redirect_uri: str | None = None) -> dict[str, Any]:
        raise CalendarProviderError("Intégration Microsoft Outlook en cours de déploiement.")

    async def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        raise CalendarProviderError("Intégration Microsoft Outlook en cours de déploiement.")

    async def list_events(
        self,
        credentials: dict[str, Any],
        start_time: datetime,
        end_time: datetime,
        calendar_id: str = "primary",
    ) -> list[dict[str, Any]]:
        return []

    async def create_event(
        self,
        credentials: dict[str, Any],
        event: CalendarEventData,
        calendar_id: str = "primary",
    ) -> str:
        raise CalendarProviderError("Intégration Microsoft Outlook non connectée.")

    async def update_event(
        self,
        credentials: dict[str, Any],
        external_event_id: str,
        event: CalendarEventData,
        calendar_id: str = "primary",
    ) -> bool:
        return False

    async def delete_event(
        self,
        credentials: dict[str, Any],
        external_event_id: str,
        calendar_id: str = "primary",
    ) -> bool:
        return False

    async def check_busy_slots(
        self,
        credentials: dict[str, Any],
        start_time: datetime,
        end_time: datetime,
        calendar_id: str = "primary",
    ) -> list[BusySlot]:
        return []
