"""Outlook Graph token exchange and employee guidance without invented data."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from io import BytesIO

import pytest

from backend.app.services.calendar.base import CalendarEventData
from backend.app.services.calendar.outlook_provider import OutlookCalendarProvider


class _FakeResp(BytesIO):
    def __init__(self, payload: dict, status: int = 200):
        super().__init__(json.dumps(payload).encode("utf-8"))
        self.status = status


@pytest.mark.asyncio
async def test_outlook_exchange_code_uses_graph(monkeypatch):
    calls: list[str] = []

    @asynccontextmanager
    async def fake_open(request, *, timeout):
        calls.append(request.full_url)
        if "oauth2/v2.0/token" in request.full_url:
            payload = {"access_token": "tok", "refresh_token": "ref", "token_type": "Bearer"}
        else:
            payload = {"mail": "owner@example.ca"}
        yield _FakeResp(payload)

    monkeypatch.setattr("backend.app.services.calendar.outlook_provider._open_response", fake_open)
    provider = OutlookCalendarProvider("id", "secret", "https://api.avenqo.ca/callback")
    tokens = await provider.exchange_code("auth-code")
    assert tokens["access_token"] == "tok"
    assert tokens["account_email"] == "owner@example.ca"
    assert any("oauth2" in url for url in calls)


@pytest.mark.asyncio
async def test_outlook_create_event_requires_graph_id(monkeypatch):
    @asynccontextmanager
    async def fake_open(request, *, timeout):
        yield _FakeResp({"id": "AAMkAGI="})

    monkeypatch.setattr("backend.app.services.calendar.outlook_provider._open_response", fake_open)
    provider = OutlookCalendarProvider("id", "secret", "https://api.avenqo.ca/callback")
    event_id = await provider.create_event(
        {"access_token": "tok"},
        CalendarEventData(
            title="Vidange",
            start_time=datetime(2026, 10, 11, 14, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 10, 11, 15, 0, tzinfo=timezone.utc),
            client_name="Garage",
        ),
    )
    assert event_id == "AAMkAGI="
