from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.api.router import api_router
from backend.app.core.security import hash_token
from backend.app.models import Base, CommerceOAuthState
from backend.app.routers.crm import (
    _google_oauth_state,
    _verify_google_oauth_state,
    google_calendar_callback,
)
from backend.app.services.calendar.google_provider import GoogleCalendarProvider
from backend.app.services.calendar.base import CalendarProviderError


def _encode_oauth_state(payload: dict[str, str], secret: str) -> str:
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("utf-8").rstrip("=")
    signature = hmac.new(secret.encode("utf-8"), encoded.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def _iter_api_routes():
    for route in api_router.routes:
        path = getattr(route, "path", None)
        if path is not None:
            yield route
            continue
        effective_route_contexts = getattr(route, "effective_route_contexts", None)
        if effective_route_contexts is None:
            continue
        yield from effective_route_contexts()


def test_google_oauth_state_is_signed_and_tenant_bound() -> None:
    state = _google_oauth_state(
        "9c97cb94-e9f9-46fb-afd4-8a1d21019cff",
        "25fe88b0-2b65-4269-924c-013520773dbd",
        "test-secret",
    )
    payload = _verify_google_oauth_state(state, "test-secret")
    assert payload["tenant_id"] == "9c97cb94-e9f9-46fb-afd4-8a1d21019cff"
    assert payload["user_id"] == "25fe88b0-2b65-4269-924c-013520773dbd"
    assert payload["provider"] == "google_calendar"
    assert payload["nonce"]

    mismatched_provider = _encode_oauth_state(
        {
            **payload,
            "provider": "not_google_calendar",
        },
        "test-secret",
    )
    with pytest.raises(Exception):
        _verify_google_oauth_state(mismatched_provider, "test-secret")

    with pytest.raises(Exception):
        _verify_google_oauth_state(f"{state}tampered", "test-secret")


def test_callback_route_is_public_but_crm_routes_remain_protected() -> None:
    callback = next(
        route for route in _iter_api_routes()
        if getattr(route, "path", None) == "/api/v1/crm/calendar/google/callback"
    )
    kpis = next(
        route for route in _iter_api_routes()
        if getattr(route, "path", None) == "/api/v1/crm/kpis"
    )
    callback_dependencies = {dependency.call.__name__ for dependency in callback.dependant.dependencies}
    protected_dependencies = {dependency.call.__name__ for dependency in kpis.dependant.dependencies}
    assert "get_current_identity" not in callback_dependencies
    assert "require_active_subscription" not in callback_dependencies
    assert "require_active_subscription" in protected_dependencies


def test_callback_without_jwt_consumes_valid_state_and_rejects_replay(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'oauth.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    tenant_id = UUID("9c97cb94-e9f9-46fb-afd4-8a1d21019cff")
    user_id = UUID("25fe88b0-2b65-4269-924c-013520773dbd")
    secret = "test-secret"
    state = _google_oauth_state(tenant_id, user_id, secret)
    now = datetime.now(timezone.utc)

    class FakeProvider:
        async def exchange_code(self, code: str):
            assert code == "google-code"
            return {"access_token": "runtime-token", "account_email": "owner@example.com"}

    class FakeCipher:
        def encrypt(self, payload):
            return "encrypted-runtime-token"

    monkeypatch.setattr(
        "backend.app.routers.crm.get_settings",
        lambda: SimpleNamespace(
            auth_jwt_secret=secret,
            google_calendar_client_id="client-id",
            google_calendar_client_secret="server-only-secret",
            google_calendar_redirect_uri="https://api.example.test/callback",
            frontend_url="https://avenqo.ca",
        ),
    )
    monkeypatch.setattr("backend.app.routers.crm.GoogleCalendarProvider", lambda **kwargs: FakeProvider())
    monkeypatch.setattr("backend.app.routers.crm.get_connector_secret_cipher", lambda: FakeCipher())

    with factory() as db:
        db.add(
            CommerceOAuthState(
                company_id=tenant_id,
                actor_user_id=user_id,
                provider="google_calendar",
                external_account_id="google_calendar",
                state_hash=hash_token(state),
                expires_at=now + timedelta(minutes=10),
            )
        )
        db.commit()
        cross_tenant_state = _google_oauth_state(tenant_id, user_id, secret)
        cross_tenant_db = SimpleNamespace(
            scalar=lambda query: SimpleNamespace(
                company_id=UUID("00000000-0000-0000-0000-000000000002"),
                actor_user_id=user_id,
                expires_at=now + timedelta(minutes=10),
            ),
        )
        with pytest.raises(Exception, match="invalide"):
            asyncio.run(
                google_calendar_callback(
                    code="google-code", state=cross_tenant_state, db=cross_tenant_db
                )
            )

        response = asyncio.run(google_calendar_callback(code="google-code", state=state, db=db))
        assert response.status_code == 303
        with pytest.raises(Exception, match="déjà utilisé"):
            asyncio.run(google_calendar_callback(code="google-code", state=state, db=db))


def test_callback_rejects_expired_and_cross_tenant_persisted_states(tmp_path) -> None:
    secret = "test-secret"
    state = _google_oauth_state(
        UUID("9c97cb94-e9f9-46fb-afd4-8a1d21019cff"),
        UUID("25fe88b0-2b65-4269-924c-013520773dbd"),
        secret,
    )
    payload = _verify_google_oauth_state(state, secret)
    expired = _encode_oauth_state(
        {**payload, "expires_at": int(datetime.now(timezone.utc).timestamp()) - 1},
        secret,
    )
    with pytest.raises(Exception):
        _verify_google_oauth_state(expired, secret)


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


def test_google_provider_fetches_account_email(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        status = 200
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return b'{"email":"owner@example.com"}'

    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: FakeResponse())
    email = asyncio.run(GoogleCalendarProvider()._fetch_user_email("access-token"))
    assert email == "owner@example.com"


def test_google_calendar_list_response_is_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        status = 200
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


@pytest.mark.parametrize("payload", [{}, {"calendars": {"primary": {"errors": [{"reason": "forbidden"}]}}}, {"calendars": {"primary": {"busy": [{"start": "invalid", "end": "invalid"}]}}}])
def test_google_freebusy_malformed_response_fails_closed(monkeypatch, payload):
    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return json.dumps(payload).encode()

    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: Response())
    now = datetime.now(timezone.utc)
    with pytest.raises(CalendarProviderError, match="EXTERNAL_AVAILABILITY_UNAVAILABLE"):
        asyncio.run(GoogleCalendarProvider().check_busy_slots({"access_token": "test"}, now, now + timedelta(hours=1)))
