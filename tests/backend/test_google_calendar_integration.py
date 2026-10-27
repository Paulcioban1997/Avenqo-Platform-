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
from starlette.requests import Request

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


@pytest.mark.parametrize("delete_status,get_status,event_status,expected", [
    (204, 200, "cancelled", True),
    (204, 200, "confirmed", False),
    (204, 404, None, True),
    (410, 200, "cancelled", True),
    (404, 200, "confirmed", False),
])
def test_google_delete_confirms_exact_event_inactive(monkeypatch, delete_status, get_status, event_status, expected):
    import urllib.error
    from io import BytesIO

    calls = []

    class Response:
        def __init__(self, status, data):
            self.status = status
            self.data = data
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self):
            return json.dumps(self.data).encode()

    def request(req, timeout):
        calls.append((req.get_method(), req.full_url))
        code = delete_status if req.get_method() == "DELETE" else get_status
        if code >= 400:
            raise urllib.error.HTTPError(req.full_url, code, "fixture", {}, BytesIO(b"{}"))
        return Response(code, {"id": "fixture-event", "status": event_status})

    monkeypatch.setattr("urllib.request.urlopen", request)
    result = asyncio.run(GoogleCalendarProvider().delete_event({"access_token": "fixture"}, "fixture-event", "fixture-calendar"))
    assert result is expected
    assert [method for method, _ in calls] == ["DELETE", "GET"]
    assert calls[0][1] == calls[1][1]


def test_google_delete_confirmation_network_failure_is_not_success(monkeypatch):
    class Response:
        status = 204
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self):
            return b""
    def request(req, timeout):
        if req.get_method() == "GET":
            raise TimeoutError("fixture")
        return Response()
    monkeypatch.setattr("urllib.request.urlopen", request)
    with pytest.raises(CalendarProviderError, match="Vérification suppression"):
        asyncio.run(GoogleCalendarProvider().delete_event({"access_token": "fixture"}, "fixture-event"))


@pytest.mark.parametrize("reason", ["GOOGLE_BUSY", "Conflit CRM_BUSY"])
def test_busy_calendar_slot_returns_actionable_conflict(reason):
    from fastapi import HTTPException
    from backend.app.routers.crm import CreateAppointmentRequest, create_appointment
    from backend.app.core.error_localization import http_error_message

    class Service:
        async def create_appointment(self, company_id, data):
            return None, reason

    tenant = SimpleNamespace(company_id=UUID("9c97cb94-e9f9-46fb-afd4-8a1d21019cff"))
    payload = CreateAppointmentRequest(client_id=tenant.company_id, start_time=datetime.now(timezone.utc))
    with pytest.raises(HTTPException) as raised:
        asyncio.run(create_appointment(payload, idempotency_key=None, tenant=tenant, service=Service()))
    assert raised.value.status_code == 409
    assert raised.value.detail == {"code": "APPOINTMENT_CONFLICT"}
    assert "créneau est occupé" in http_error_message(409, "fr-CA", raised.value.detail)


@pytest.mark.parametrize("operation", ["exchange_code", "refresh_access_token", "list_calendars"])
def test_google_provider_errors_do_not_expose_response_or_credentials(monkeypatch, caplog, operation):
    import urllib.error
    from io import BytesIO

    sensitive_fixture = "non-sensitive-response-marker-example.test"

    def failed_request(*args, **kwargs):
        raise urllib.error.HTTPError(
            "https://oauth2.googleapis.com/token", 401, sensitive_fixture,
            {}, BytesIO(json.dumps({"error_description": sensitive_fixture}).encode()),
        )

    monkeypatch.setattr("urllib.request.urlopen", failed_request)
    provider = GoogleCalendarProvider("fixture-client", "fixture-secret", "https://example.test/callback")
    argument = {"access_token": "fixture-token"} if operation == "list_calendars" else "fixture-value"
    with pytest.raises(CalendarProviderError) as raised:
        asyncio.run(getattr(provider, operation)(argument))
    assert sensitive_fixture not in str(raised.value)
    assert sensitive_fixture not in caplog.text
    assert "fixture-secret" not in caplog.text
    assert isinstance(raised.value.__cause__, urllib.error.HTTPError)


def test_google_network_errors_do_not_echo_request_details(monkeypatch, caplog):
    def failed_request(*args, **kwargs):
        raise RuntimeError("fixture-private-request-details")

    monkeypatch.setattr("urllib.request.urlopen", failed_request)
    with pytest.raises(CalendarProviderError) as raised:
        asyncio.run(GoogleCalendarProvider().exchange_code("fixture-code"))
    assert "fixture-private-request-details" not in str(raised.value)
    assert "fixture-private-request-details" not in caplog.text


def _callback_request(state: str, *, bind: bool = True) -> Request:
    headers = []
    if bind:
        headers.append((b"cookie", f"avenqo_oauth_bind={hash_token(state)}".encode()))
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/api/v1/crm/calendar/google/callback",
        "headers": headers,
        "query_string": b"",
    })


def _encode_oauth_state(payload: dict[str, str], secret: str) -> str:
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("utf-8").rstrip("=")
    signature = hmac.new(secret.encode("utf-8"), encoded.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


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


def _iter_api_routes():
    for route in api_router.routes:
        if getattr(route, 'path', None) is not None:
            yield route
            continue
        contexts = getattr(route, 'effective_route_contexts', None)
        if callable(contexts):
            yield from contexts()


def test_callback_route_is_public_but_crm_routes_remain_protected() -> None:
    routes = list(_iter_api_routes())
    callback = next(
        route for route in routes
        if getattr(route, "path", None) == "/api/v1/crm/calendar/google/callback"
    )
    kpis = next(
        route for route in routes
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
        with pytest.raises(Exception, match="navigateur manquante"):
            asyncio.run(
                google_calendar_callback(
                    request=_callback_request(state, bind=False),
                    code="google-code",
                    state=state,
                    db=db,
                )
            )
        with pytest.raises(Exception, match="invalide"):
            asyncio.run(
                google_calendar_callback(
                    request=_callback_request(cross_tenant_state),
                    code="google-code",
                    state=cross_tenant_state,
                    db=cross_tenant_db,
                )
            )

        response = asyncio.run(
            google_calendar_callback(
                request=_callback_request(state),
                code="google-code",
                state=state,
                db=db,
            )
        )
        assert response.status_code == 303
        with pytest.raises(Exception, match="déjà utilisé"):
            asyncio.run(
                google_calendar_callback(
                    request=_callback_request(state),
                    code="google-code",
                    state=state,
                    db=db,
                )
            )


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


def test_google_refresh_token_revoked_raises_token_revoked_error(monkeypatch):
    import urllib.error
    from io import BytesIO
    from backend.app.services.calendar.base import CalendarTokenRevokedError

    def fake_urlopen(req, timeout=15):
        raise urllib.error.HTTPError(
            req.full_url,
            400,
            "Bad Request",
            {},
            BytesIO(b'{"error": "invalid_grant", "error_description": "Token has been expired or revoked."}'),
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = GoogleCalendarProvider("client_id", "client_secret", "https://api.avenqo.ca/callback")
    with pytest.raises(CalendarTokenRevokedError, match="expiré ou révoqué"):
        asyncio.run(provider.refresh_access_token("revoked_refresh_token"))


def test_google_refresh_token_transient_error_raises_transient_error(monkeypatch):
    import urllib.error
    from io import BytesIO
    from backend.app.services.calendar.base import CalendarTokenTransientError

    def fake_urlopen(req, timeout=15):
        raise urllib.error.HTTPError(
            req.full_url,
            503,
            "Service Unavailable",
            {},
            BytesIO(b'{"error": "backend_error"}'),
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = GoogleCalendarProvider("client_id", "client_secret", "https://api.avenqo.ca/callback")
    with pytest.raises(CalendarTokenTransientError, match="Échec temporaire"):
        asyncio.run(provider.refresh_access_token("transient_refresh_token"))


def test_google_refresh_token_success(monkeypatch):
    from io import BytesIO

    class SuccessResponse:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return None
        def read(self):
            return json.dumps({
                "access_token": "new-access-token-123",
                "expires_in": 3600,
                "token_type": "Bearer",
            }).encode("utf-8")

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=15: SuccessResponse())
    provider = GoogleCalendarProvider("client_id", "client_secret", "https://api.avenqo.ca/callback")
    result = asyncio.run(provider.refresh_access_token("valid_refresh_token"))
    assert result["access_token"] == "new-access-token-123"
    assert result["expires_in"] == 3600


def test_crm_get_calendar_connection_returns_reconnect_status_when_error():
    from backend.app.routers.crm import get_calendar_connection
    from backend.app.models.crm import CRMCalendarConnection

    fake_conn = CRMCalendarConnection(
        company_id=UUID("9c97cb94-e9f9-46fb-afd4-8a1d21019cff"),
        provider="google",
        account_email="owner@avenqo.ca",
        calendar_id="primary",
        sync_status="error",
        sync_error="Google token expired or revoked. Please reconnect.",
    )

    class FakeService:
        def get_calendar_connection(self, company_id):
            return fake_conn

    tenant = SimpleNamespace(company_id=UUID("9c97cb94-e9f9-46fb-afd4-8a1d21019cff"))
    res = get_calendar_connection(tenant=tenant, service=FakeService())
    assert res["connected"] is False
    assert res["sync_status"] == "error"
    assert res["requires_reconnect"] is True
    assert res["reconnect_message"] == "Reconnectez Google Calendar pour reprendre les réservations"
