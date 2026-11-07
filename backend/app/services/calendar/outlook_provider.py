"""Microsoft Outlook / Graph Calendar — implémentation réelle, pas un stub."""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from io import BytesIO
from typing import Any

from backend.app.services.calendar.base import (
    BusySlot,
    CalendarEventData,
    CalendarProvider,
    CalendarProviderError,
)

logger = logging.getLogger(__name__)

MS_AUTH_ENDPOINT = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
MS_TOKEN_ENDPOINT = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
GRAPH_BASE = "https://graph.microsoft.com/v1.0"
CALENDAR_SCOPES = "Calendars.ReadWrite User.Read offline_access"


@asynccontextmanager
async def _open_response(request, *, timeout):
    def read_response():
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read(), response.status

    body, status = await asyncio.to_thread(read_response)
    with BytesIO(body) as response:
        response.status = status
        yield response


class OutlookCalendarProvider(CalendarProvider):
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
        params = {
            "client_id": self._client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri or self._redirect_uri,
            "scope": CALENDAR_SCOPES,
            "state": state,
            "response_mode": "query",
        }
        return f"{MS_AUTH_ENDPOINT}?{urllib.parse.urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str | None = None) -> dict[str, Any]:
        payload = await self._token_request(
            {
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri or self._redirect_uri,
                "scope": CALENDAR_SCOPES,
            }
        )
        payload["account_email"] = await self._fetch_user_email(payload.get("access_token", ""))
        return payload

    async def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        return await self._token_request(
            {
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
                "scope": CALENDAR_SCOPES,
            }
        )

    async def _token_request(self, fields: dict[str, str]) -> dict[str, Any]:
        req = urllib.request.Request(
            MS_TOKEN_ENDPOINT,
            data=urllib.parse.urlencode(fields).encode("utf-8"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            async with _open_response(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8")
            logger.error("Outlook token request failed: %s %s", exc.code, body)
            raise CalendarProviderError("Échec de l'authentification Microsoft Graph") from exc
        except Exception as exc:
            raise CalendarProviderError("Erreur de connexion avec Microsoft") from exc

    async def _fetch_user_email(self, access_token: str) -> str:
        if not access_token:
            return ""
        req = urllib.request.Request(
            f"{GRAPH_BASE}/me",
            headers={"Authorization": f"Bearer {access_token}"},
            method="GET",
        )
        try:
            async with _open_response(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return str(data.get("mail") or data.get("userPrincipalName") or "")
        except Exception:
            return ""

    def _auth_headers(self, credentials: dict[str, Any]) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {credentials.get('access_token', '')}",
            "Content-Type": "application/json",
        }

    def _event_body(self, event: CalendarEventData) -> dict[str, Any]:
        body: dict[str, Any] = {
            "subject": event.title,
            "body": {
                "contentType": "text",
                "content": event.description or f"Rendez-vous Avenqo avec {event.client_name or 'le client'}",
            },
            "start": {"dateTime": event.start_time.astimezone(timezone.utc).isoformat(), "timeZone": "UTC"},
            "end": {"dateTime": event.end_time.astimezone(timezone.utc).isoformat(), "timeZone": "UTC"},
        }
        if event.location:
            body["location"] = {"displayName": event.location}
        if event.attendee_email:
            body["attendees"] = [
                {
                    "emailAddress": {"address": event.attendee_email, "name": event.client_name or ""},
                    "type": "required",
                }
            ]
        return body

    async def list_events(
        self,
        credentials: dict[str, Any],
        start_time: datetime,
        end_time: datetime,
        calendar_id: str = "primary",
    ) -> list[dict[str, Any]]:
        params = urllib.parse.urlencode(
            {
                "startDateTime": start_time.astimezone(timezone.utc).isoformat(),
                "endDateTime": end_time.astimezone(timezone.utc).isoformat(),
            }
        )
        req = urllib.request.Request(
            f"{GRAPH_BASE}/me/calendarView?{params}",
            headers=self._auth_headers(credentials),
            method="GET",
        )
        try:
            async with _open_response(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return list(data.get("value") or [])
        except urllib.error.HTTPError as exc:
            raise CalendarProviderError(f"Microsoft Graph error ({exc.code})") from exc

    async def create_event(
        self,
        credentials: dict[str, Any],
        event: CalendarEventData,
        calendar_id: str = "primary",
    ) -> str:
        req = urllib.request.Request(
            f"{GRAPH_BASE}/me/events",
            data=json.dumps(self._event_body(event)).encode("utf-8"),
            headers=self._auth_headers(credentials),
            method="POST",
        )
        try:
            async with _open_response(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            event_id = str(data.get("id") or "")
            if not event_id:
                raise CalendarProviderError("Microsoft Graph n'a pas renvoyé d'identifiant d'événement")
            return event_id
        except urllib.error.HTTPError as exc:
            raise CalendarProviderError(f"Création Outlook impossible ({exc.code})") from exc

    async def update_event(
        self,
        credentials: dict[str, Any],
        external_event_id: str,
        event: CalendarEventData,
        calendar_id: str = "primary",
    ) -> bool:
        req = urllib.request.Request(
            f"{GRAPH_BASE}/me/events/{urllib.parse.quote(external_event_id)}",
            data=json.dumps(self._event_body(event)).encode("utf-8"),
            headers=self._auth_headers(credentials),
            method="PATCH",
        )
        try:
            async with _open_response(req, timeout=15) as resp:
                resp.read()
            return True
        except urllib.error.HTTPError as exc:
            raise CalendarProviderError(f"Mise à jour Outlook impossible ({exc.code})") from exc

    async def delete_event(
        self,
        credentials: dict[str, Any],
        external_event_id: str,
        calendar_id: str = "primary",
    ) -> bool:
        req = urllib.request.Request(
            f"{GRAPH_BASE}/me/events/{urllib.parse.quote(external_event_id)}",
            headers=self._auth_headers(credentials),
            method="DELETE",
        )
        try:
            async with _open_response(req, timeout=15) as resp:
                resp.read()
            return True
        except urllib.error.HTTPError as exc:
            raise CalendarProviderError(f"Suppression Outlook impossible ({exc.code})") from exc

    async def check_busy_slots(
        self,
        credentials: dict[str, Any],
        start_time: datetime,
        end_time: datetime,
        calendar_id: str = "primary",
    ) -> list[BusySlot]:
        events = await self.list_events(credentials, start_time, end_time, calendar_id)
        slots: list[BusySlot] = []
        for item in events:
            start = item.get("start", {}).get("dateTime")
            finish = item.get("end", {}).get("dateTime")
            if not start or not finish:
                continue
            slots.append(
                BusySlot(
                    start_time=datetime.fromisoformat(str(start).replace("Z", "+00:00")),
                    end_time=datetime.fromisoformat(str(finish).replace("Z", "+00:00")),
                )
            )
        return slots
