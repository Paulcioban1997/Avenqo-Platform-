"""Google Calendar API v3 provider implementation for Avenqo CRM AI."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any
import urllib.parse
import urllib.request
import urllib.error

from backend.app.services.calendar.base import (
    BusySlot,
    CalendarEventData,
    CalendarProvider,
    CalendarProviderError,
)

logger = logging.getLogger(__name__)

GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_CALENDAR_BASE_URL = "https://www.googleapis.com/calendar/v3"
CALENDAR_SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
]


class GoogleCalendarProvider(CalendarProvider):
    """Production Google Calendar API v3 integration with OAuth 2.0."""

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
        return "google"

    def get_auth_url(self, state: str, redirect_uri: str | None = None) -> str:
        """Generates Google OAuth 2.0 consent URL."""
        effective_redirect = redirect_uri or self._redirect_uri
        params = {
            "client_id": self._client_id,
            "redirect_uri": effective_redirect,
            "response_type": "code",
            "scope": " ".join(CALENDAR_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        return f"{GOOGLE_AUTH_ENDPOINT}?{urllib.parse.urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str | None = None) -> dict[str, Any]:
        """Exchanges authorization code for access and refresh tokens."""
        effective_redirect = redirect_uri or self._redirect_uri
        data = urllib.parse.urlencode({
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": effective_redirect,
        }).encode("utf-8")

        req = urllib.request.Request(
            GOOGLE_TOKEN_ENDPOINT,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                token_payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8")
            logger.error("Google token exchange failed: %s %s", exc.code, err_body)
            raise CalendarProviderError(f"Échec de l'authentification Google OAuth: {err_body}") from exc
        except Exception as exc:
            logger.error("Google token network error: %s", exc)
            raise CalendarProviderError(f"Erreur de connexion avec Google: {exc}") from exc

        # Fetch user email with access token
        account_email = await self._fetch_user_email(token_payload.get("access_token", ""))
        token_payload["account_email"] = account_email
        return token_payload

    async def _fetch_user_email(self, access_token: str) -> str:
        if not access_token:
            return ""
        req = urllib.request.Request(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                info = json.loads(resp.read().decode("utf-8"))
                return info.get("email", "")
        except Exception:
            return ""

    async def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        """Refreshes expired access token using stored refresh token."""
        data = urllib.parse.urlencode({
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }).encode("utf-8")

        req = urllib.request.Request(
            GOOGLE_TOKEN_ENDPOINT,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            raise CalendarProviderError(f"Échec du rafraîchissement du token Google: {exc}") from exc

    def _auth_headers(self, credentials: dict[str, Any]) -> dict[str, str]:
        token = credentials.get("access_token", "")
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def list_events(
        self,
        credentials: dict[str, Any],
        start_time: datetime,
        end_time: datetime,
        calendar_id: str = "primary",
    ) -> list[dict[str, Any]]:
        """Reads events from Google Calendar between start and end times."""
        time_min = start_time.isoformat()
        time_max = end_time.isoformat()
        encoded_cal = urllib.parse.quote(calendar_id, safe="")
        url = (
            f"{GOOGLE_CALENDAR_BASE_URL}/calendars/{encoded_cal}/events"
            f"?timeMin={urllib.parse.quote(time_min)}"
            f"&timeMax={urllib.parse.quote(time_max)}"
            f"&singleEvents=true&orderBy=startTime"
        )
        req = urllib.request.Request(url, headers=self._auth_headers(credentials), method="GET")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("items", [])
        except urllib.error.HTTPError as exc:
            raise CalendarProviderError(f"Google Calendar API error ({exc.code}): {exc.read().decode('utf-8')}") from exc
        except Exception as exc:
            raise CalendarProviderError(f"Erreur réseau Google Calendar: {exc}") from exc

    async def create_event(
        self,
        credentials: dict[str, Any],
        event: CalendarEventData,
        calendar_id: str = "primary",
    ) -> str:
        """Creates event in Google Calendar and returns the Google Event ID."""
        encoded_cal = urllib.parse.quote(calendar_id, safe="")
        url = f"{GOOGLE_CALENDAR_BASE_URL}/calendars/{encoded_cal}/events"

        body: dict[str, Any] = {
            "summary": event.title,
            "description": event.description or f"Rendez-vous Avenqo avec {event.client_name or 'le client'}",
            "start": {
                "dateTime": event.start_time.isoformat(),
            },
            "end": {
                "dateTime": event.end_time.isoformat(),
            },
        }
        if event.location:
            body["location"] = event.location
        if event.attendee_email:
            body["attendees"] = [{"email": event.attendee_email, "displayName": event.client_name or ""}]

        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers=self._auth_headers(credentials),
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                created = json.loads(resp.read().decode("utf-8"))
                return created.get("id", "")
        except urllib.error.HTTPError as exc:
            raise CalendarProviderError(f"Erreur création événement Google ({exc.code}): {exc.read().decode('utf-8')}") from exc
        except Exception as exc:
            raise CalendarProviderError(f"Erreur création événement Google: {exc}") from exc

    async def update_event(
        self,
        credentials: dict[str, Any],
        external_event_id: str,
        event: CalendarEventData,
        calendar_id: str = "primary",
    ) -> bool:
        """Updates event in Google Calendar."""
        if not external_event_id:
            return False
        encoded_cal = urllib.parse.quote(calendar_id, safe="")
        encoded_event = urllib.parse.quote(external_event_id, safe="")
        url = f"{GOOGLE_CALENDAR_BASE_URL}/calendars/{encoded_cal}/events/{encoded_event}"

        body: dict[str, Any] = {
            "summary": event.title,
            "description": event.description or "",
            "start": {"dateTime": event.start_time.isoformat()},
            "end": {"dateTime": event.end_time.isoformat()},
        }
        if event.location:
            body["location"] = event.location

        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers=self._auth_headers(credentials),
            method="PATCH",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.status in {200, 204}
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return False
            raise CalendarProviderError(f"Erreur modification événement Google ({exc.code}): {exc.read().decode('utf-8')}") from exc
        except Exception as exc:
            raise CalendarProviderError(f"Erreur modification événement Google: {exc}") from exc

    async def delete_event(
        self,
        credentials: dict[str, Any],
        external_event_id: str,
        calendar_id: str = "primary",
    ) -> bool:
        """Deletes/cancels event in Google Calendar."""
        if not external_event_id:
            return False
        encoded_cal = urllib.parse.quote(calendar_id, safe="")
        encoded_event = urllib.parse.quote(external_event_id, safe="")
        url = f"{GOOGLE_CALENDAR_BASE_URL}/calendars/{encoded_cal}/events/{encoded_event}"

        req = urllib.request.Request(
            url,
            headers=self._auth_headers(credentials),
            method="DELETE",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.status in {200, 204}
        except urllib.error.HTTPError as exc:
            if exc.code in {404, 410}:
                return True
            raise CalendarProviderError(f"Erreur suppression événement Google ({exc.code}): {exc.read().decode('utf-8')}") from exc
        except Exception as exc:
            raise CalendarProviderError(f"Erreur suppression événement Google: {exc}") from exc

    async def check_busy_slots(
        self,
        credentials: dict[str, Any],
        start_time: datetime,
        end_time: datetime,
        calendar_id: str = "primary",
    ) -> list[BusySlot]:
        """Queries Google Calendar FreeBusy API to find busy periods."""
        url = f"{GOOGLE_CALENDAR_BASE_URL}/freeBusy"
        body = {
            "timeMin": start_time.isoformat(),
            "timeMax": end_time.isoformat(),
            "items": [{"id": calendar_id}],
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers=self._auth_headers(credentials),
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                cal_data = data.get("calendars", {}).get(calendar_id, {})
                busy_list = cal_data.get("busy", [])
                slots: list[BusySlot] = []
                for b in busy_list:
                    s_str = b.get("start", "")
                    e_str = b.get("end", "")
                    if s_str and e_str:
                        s_dt = datetime.fromisoformat(s_str.replace("Z", "+00:00"))
                        e_dt = datetime.fromisoformat(e_str.replace("Z", "+00:00"))
                        slots.append(BusySlot(start_time=s_dt, end_time=e_dt))
                return slots
        except Exception as exc:
            logger.warning("Freebusy check failed, fallback to empty: %s", exc)
            return []
