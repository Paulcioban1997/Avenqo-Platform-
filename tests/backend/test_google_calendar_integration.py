from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from backend.app.routers.crm import _google_oauth_state, _verify_google_oauth_state
from backend.app.services.calendar.google_provider import GoogleCalendarProvider


def test_google_oauth_state_is_signed_and_tenant_bound() -> None:
    state = _google_oauth_state(
        "9c97cb94-e9f9-46fb-afd4-8a1d21019cff",
        "25fe88b0-2b65-4269-924c-013520773dbd",
        "test-secret",
    )
    payload = _verify_google_oauth_state(state, "test-secret")
    assert payload["tenant_id"] == "9c97cb94-e9f9-46fb-afd4-8a1d21019cff"
    assert payload["user_id"] == "25fe88b0-2b65-4269-924c-013520773dbd"

    with pytest.raises(Exception):
        _verify_google_oauth_state(f"{state}tampered", "test-secret")


def test_google_auth_url_uses_offline_calendar_scopes() -> None:
    provider = GoogleCalendarProvider(
        client_id="client-id",
        client_secret="server-only-secret",
        redirect_uri="https://api.example.test/api/v1/crm/calendar/google/callback",
    )
    url = provider.get_auth_url("signed-state")
    assert "access_type=offline" in url
    assert "prompt=consent" in url
    assert "signed-state" in url
    assert "calendar.events" in url
    assert "calendar.readonly" in url
    assert "server-only-secret" not in url


def test_google_calendar_list_response_is_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return json.dumps({
                "items": [
                    {"id": "primary", "summary": "Cabinet", "primary": True, "timeZone": "America/Toronto", "accessRole": "owner"},
                    {"id": "other", "summary": "Équipe", "primary": False, "timeZone": "America/Toronto", "accessRole": "writer"},
                    {"id": "hidden", "summary": None},
                ]
            }).encode()

    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: FakeResponse())
    calendars = asyncio.run(GoogleCalendarProvider().list_calendars({"access_token": "runtime-only"}))
    assert calendars == [
        {"id": "primary", "summary": "Cabinet", "description": None, "time_zone": "America/Toronto", "primary": True, "access_role": "owner"},
        {"id": "other", "summary": "Équipe", "description": None, "time_zone": "America/Toronto", "primary": False, "access_role": "writer"},
    ]
