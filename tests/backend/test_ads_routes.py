"""Tests for FastAPI advertising routes (/api/v1/ads/*)."""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.config.settings import Settings, get_settings
from backend.app.core.security import create_access_token
from backend.app.database import get_db
from backend.app.dependencies.commerce import ConnectorSecretCipher, get_connector_secret_cipher
from backend.app.models.base import Base
from backend.app.models.company import Company
from backend.app.models.commerce_connection import CommerceConnection, CommerceConnectionStatus
from backend.app.models.auth_session import AuthSession
from backend.app.models.user import User, UserRole
from backend.main import create_application
from tests.subscription_helpers import add_active_subscription


class DummyCipher:
    def encrypt(self, data: dict) -> str:
        return f"enc_{base64.b64encode(json.dumps(data).encode()).decode()}"

    def decrypt(self, token: str) -> dict:
        if token.startswith("enc_"):
            return json.loads(base64.b64decode(token[4:].encode()).decode())
        return json.loads(token)


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'ads_routes.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        yield session


@pytest.fixture
def test_setup(db_session):
    company = Company(
        id=uuid4(),
        name="Test Ads Co",
        slug=f"ads-{uuid4().hex[:6]}",
        email=f"ads-{uuid4().hex[:6]}@example.com",
        country="CA",
        timezone="America/Toronto",
        industry="Retail",
        subscription_plan="professional",
    )
    db_session.add(company)
    db_session.flush()
    add_active_subscription(db_session, company)

    user = User(
        id=uuid4(),
        company_id=company.id,
        first_name="Ads",
        last_name="Manager",
        email=f"user-{uuid4().hex[:6]}@example.com",
        password_hash="hash",
        role=UserRole.OWNER,
        email_verified_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    db_session.flush()

    session_id = uuid4()
    now = datetime.now(timezone.utc)
    db_session.add(
        AuthSession(
            id=session_id,
            user_id=user.id,
            token_hash=f"hash-{session_id}",
            created_at=now,
            expires_at=now.replace(year=now.year + 1),
        )
    )
    db_session.commit()

    token, _ = create_access_token(user.id, company.id, session_id)
    return {"company": company, "user": user, "token": token}


def get_test_client(db_session, settings: Settings) -> TestClient:
    get_settings.cache_clear()
    app = create_application()

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_connector_secret_cipher] = lambda: DummyCipher()
    return TestClient(app)


def test_ads_status_unauthenticated_fails(db_session):
    settings = Settings(auth_jwt_secret="a" * 32)
    client = get_test_client(db_session, settings)
    resp = client.get("/api/v1/ads/status")
    assert resp.status_code == 401


def test_ads_status_authenticated_returns_providers(db_session, test_setup):
    settings = Settings(auth_jwt_secret="a" * 32)
    client = get_test_client(db_session, settings)
    headers = {"Authorization": f"Bearer {test_setup['token']}"}

    resp = client.get("/api/v1/ads/status", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "google_ads" in data
    assert "meta_ads" in data
    assert data["google_ads"]["connected"] is False
    assert data["google_ads"]["configured"] is False
    assert "GOOGLE_ADS_CLIENT_ID" in data["google_ads"]["setup_instructions"]


def test_google_ads_auth_url_blocked_when_unconfigured(db_session, test_setup):
    settings = Settings(auth_jwt_secret="a" * 32)
    client = get_test_client(db_session, settings)
    headers = {"Authorization": f"Bearer {test_setup['token']}"}

    resp = client.get("/api/v1/ads/google/auth-url", headers=headers)
    assert resp.status_code == 503
    err = resp.json()
    assert err["error"]["code"] == "ADS_CONFIGURATION_MISSING"
    assert err["error"]["details"]["status"] == "BLOCKED"


def test_meta_ads_auth_url_blocked_when_unconfigured(db_session, test_setup):
    settings = Settings(auth_jwt_secret="a" * 32)
    client = get_test_client(db_session, settings)
    headers = {"Authorization": f"Bearer {test_setup['token']}"}

    resp = client.get("/api/v1/ads/meta/auth-url", headers=headers)
    assert resp.status_code == 503
    err = resp.json()
    assert err["error"]["code"] == "ADS_CONFIGURATION_MISSING"
    assert err["error"]["details"]["status"] == "BLOCKED"


def test_google_ads_auth_url_success_when_configured(db_session, test_setup):
    settings = Settings(
        auth_jwt_secret="a" * 32,
        google_ads_client_id="gid-1234.apps.googleusercontent.com",
        google_ads_client_secret="gsecret-5678",
        google_ads_developer_token="devtoken-9999",
        google_ads_redirect_uri="https://api.avenqo.ca/api/v1/ads/google/callback",
    )
    client = get_test_client(db_session, settings)
    headers = {"Authorization": f"Bearer {test_setup['token']}"}

    resp = client.get("/api/v1/ads/google/auth-url", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "auth_url" in data
    assert "state" in data
    assert "https://accounts.google.com/o/oauth2/v2/auth" in data["auth_url"]
    assert "gid-1234" in data["auth_url"]


def test_meta_ads_auth_url_success_when_configured(db_session, test_setup):
    settings = Settings(
        auth_jwt_secret="a" * 32,
        meta_ads_app_id="meta-app-1111",
        meta_ads_app_secret="meta-sec-2222",
        meta_ads_redirect_uri="https://api.avenqo.ca/api/v1/ads/meta/callback",
    )
    client = get_test_client(db_session, settings)
    headers = {"Authorization": f"Bearer {test_setup['token']}"}

    resp = client.get("/api/v1/ads/meta/auth-url", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "auth_url" in data
    assert "https://www.facebook.com/v20.0/dialog/oauth" in data["auth_url"]
    assert "meta-app-1111" in data["auth_url"]


def test_callback_tampered_state_redirects_with_error(db_session):
    settings = Settings(auth_jwt_secret="a" * 32, frontend_url="https://avenqo.ca")
    client = get_test_client(db_session, settings)

    resp = client.get("/api/v1/ads/google/callback?code=abc&state=tampered_state", follow_redirects=False)
    assert resp.status_code == 307
    location = resp.headers["location"]
    assert "https://avenqo.ca/marketing?google_ads=error" in location


def test_performance_summary_empty_when_no_accounts_connected(db_session, test_setup):
    settings = Settings(auth_jwt_secret="a" * 32)
    client = get_test_client(db_session, settings)
    headers = {"Authorization": f"Bearer {test_setup['token']}"}

    resp = client.get("/api/v1/ads/performance/summary", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["currency"] == "CAD"
    assert data["total_spend_cad"] == 0.0
    assert data["total_impressions"] == 0
    assert data["total_clicks"] == 0
    assert data["campaigns_count"] == 0
    assert data["providers_connected"] == []

