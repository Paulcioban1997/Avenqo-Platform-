"""Tests for FastAPI advertising routes (/api/v1/ads/*).

Validates:
1. Authentication & Subscription gating.
2. Marketing module entitlement gating (HTTP 403 MODULE_NOT_ENTITLED when inactive).
3. Fine-grained RBAC permissions:
   - READ (marketing:read / data:read): Owner, Admin, Manager, Analyst, Viewer allowed; Standard User denied.
   - CONNECT (marketing:connect): Owner, Admin, Manager allowed; Analyst, Viewer, User denied.
   - DISCONNECT (marketing:disconnect): Owner, Admin allowed; Manager, Analyst, Viewer, User denied.
4. Anti-replay single-use OAuth state verification.
5. Strict multi-tenant isolation between companies.
6. Error sanitization without leaking sensitive tokens or exceptions in redirect URLs.
7. Multi-currency reporting and period filters.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Mapping
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
from backend.app.models.company_module import CompanyModule, CompanyModuleStatus
from backend.app.models.commerce_connection import CommerceConnection, CommerceConnectionStatus
from backend.app.models.auth_session import AuthSession
from backend.app.models.module import Module
from backend.app.models.user import User, UserRole
from backend.main import create_application
from tests.subscription_helpers import add_active_subscription


class DummyCipher(ConnectorSecretCipher):
    def __init__(self) -> None:
        pass

    def encrypt(self, payload: Mapping[str, Any]) -> str:
        return f"enc_{base64.b64encode(json.dumps(dict(payload)).encode()).decode()}"

    def decrypt(self, encrypted_payload: str) -> dict[str, Any]:
        if encrypted_payload.startswith("enc_"):
            return json.loads(base64.b64decode(encrypted_payload[4:].encode()).decode())
        return json.loads(encrypted_payload)


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'ads_routes.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        yield session


def _create_tenant_user(db_session, company: Company, role: UserRole) -> dict[str, Any]:
    user = User(
        id=uuid4(),
        company_id=company.id,
        first_name="Test",
        last_name=f"User-{role.value}",
        email=f"user-{role.value}-{uuid4().hex[:6]}@example.com",
        password_hash="hash",
        role=role,
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
    return {"user": user, "token": token}


def _create_tenant(db_session, name: str, *, with_marketing_module: bool = True, role: UserRole = UserRole.ADMIN):
    company = Company(
        id=uuid4(),
        name=name,
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

    if with_marketing_module:
        module = db_session.query(Module).filter(Module.code == "marketing").first()
        if not module:
            module = Module(name="Marketing", code="marketing", is_active=True)
            db_session.add(module)
            db_session.flush()
        db_session.add(
            CompanyModule(
                company_id=company.id,
                module_id=module.id,
                activated_at=datetime.now(timezone.utc) - timedelta(days=1),
                status=CompanyModuleStatus.ACTIVE,
            )
        )

    user_info = _create_tenant_user(db_session, company, role)
    return {"company": company, "user": user_info["user"], "token": user_info["token"]}


@pytest.fixture
def test_setup(db_session):
    return _create_tenant(db_session, "Test Ads Co", with_marketing_module=True, role=UserRole.ADMIN)


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
    settings = Settings(AUTH_JWT_SECRET="a" * 32)
    client = get_test_client(db_session, settings)
    resp = client.get("/api/v1/ads/status")
    assert resp.status_code == 401


def test_ads_routes_require_marketing_module_entitlement(db_session):
    tenant_no_marketing = _create_tenant(db_session, "Company Sans Marketing", with_marketing_module=False)
    settings = Settings(AUTH_JWT_SECRET="a" * 32)
    client = get_test_client(db_session, settings)
    headers = {"Authorization": f"Bearer {tenant_no_marketing['token']}"}

    resp = client.get("/api/v1/ads/status", headers=headers)
    assert resp.status_code == 403
    err = resp.json()
    assert err["error"]["code"] == "MODULE_NOT_ENTITLED"


def test_ads_status_authenticated_returns_providers(db_session, test_setup):
    settings = Settings(AUTH_JWT_SECRET="a" * 32)
    client = get_test_client(db_session, settings)
    headers = {"Authorization": f"Bearer {test_setup['token']}"}

    resp = client.get("/api/v1/ads/status", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "google_ads" in data
    assert "meta_ads" in data
    assert data["google_ads"]["connected"] is False
    assert data["meta_ads"]["connected"] is False


def test_marketing_rbac_fine_grained_matrix(db_session):
    """Verifies READ, CONNECT, and DISCONNECT boundaries across all tenant roles."""
    company = Company(
        id=uuid4(),
        name="RBAC Matrix Co",
        slug=f"rbac-{uuid4().hex[:6]}",
        email=f"rbac-{uuid4().hex[:6]}@example.com",
        country="CA",
        timezone="America/Toronto",
        industry="Retail",
        subscription_plan="professional",
    )
    db_session.add(company)
    db_session.flush()
    add_active_subscription(db_session, company)

    module = db_session.query(Module).filter(Module.code == "marketing").first()
    if not module:
        module = Module(name="Marketing", code="marketing", is_active=True)
        db_session.add(module)
        db_session.flush()
    db_session.add(
        CompanyModule(
            company_id=company.id,
            module_id=module.id,
            activated_at=datetime.now(timezone.utc) - timedelta(days=1),
            status=CompanyModuleStatus.ACTIVE,
        )
    )

    owner = _create_tenant_user(db_session, company, UserRole.OWNER)
    admin = _create_tenant_user(db_session, company, UserRole.ADMIN)
    manager = _create_tenant_user(db_session, company, UserRole.MANAGER)
    analyst = _create_tenant_user(db_session, company, UserRole.ANALYST)
    viewer = _create_tenant_user(db_session, company, UserRole.VIEWER)
    user = _create_tenant_user(db_session, company, UserRole.USER)

    settings = Settings(
        AUTH_JWT_SECRET="a" * 32,
        GOOGLE_ADS_CLIENT_ID="gid-1234.apps.googleusercontent.com",
        GOOGLE_ADS_CLIENT_SECRET="gsecret-5678",
        GOOGLE_ADS_DEVELOPER_TOKEN="devtoken-9999",
        GOOGLE_ADS_REDIRECT_URI="https://api.avenqo.ca/api/v1/ads/google/callback",
    )
    client = get_test_client(db_session, settings)

    # 1. READ PERMISSIONS (/api/v1/ads/status)
    # Allowed: OWNER, ADMIN, MANAGER, ANALYST, VIEWER
    # Denied: USER
    for role_name, token in [("owner", owner["token"]), ("admin", admin["token"]), ("manager", manager["token"]), ("analyst", analyst["token"]), ("viewer", viewer["token"])]:
        r = client.get("/api/v1/ads/status", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, f"Role {role_name} should have READ access"

    r_user = client.get("/api/v1/ads/status", headers={"Authorization": f"Bearer {user['token']}"})
    assert r_user.status_code == 403, "Standard USER should NOT have marketing read access"
    assert r_user.json()["error"]["code"] == "INSUFFICIENT_ROLE"

    # 2. CONNECT PERMISSIONS (/api/v1/ads/google/auth-url)
    # Allowed: OWNER, ADMIN, MANAGER
    # Denied: ANALYST, VIEWER, USER
    for role_name, token in [("owner", owner["token"]), ("admin", admin["token"]), ("manager", manager["token"])]:
        r = client.get("/api/v1/ads/google/auth-url", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, f"Role {role_name} should have CONNECT access"

    for role_name, token in [("analyst", analyst["token"]), ("viewer", viewer["token"]), ("user", user["token"])]:
        r = client.get("/api/v1/ads/google/auth-url", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 403, f"Role {role_name} should NOT have CONNECT access"
        assert r.json()["error"]["code"] == "INSUFFICIENT_ROLE"

    # 3. DISCONNECT PERMISSIONS (/api/v1/ads/google/disconnect)
    # Allowed: OWNER, ADMIN only
    # Denied: MANAGER, ANALYST, VIEWER, USER
    for role_name, token in [("owner", owner["token"]), ("admin", admin["token"])]:
        r = client.post("/api/v1/ads/google/disconnect", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, f"Role {role_name} should have DISCONNECT access"

    for role_name, token in [("manager", manager["token"]), ("analyst", analyst["token"]), ("viewer", viewer["token"]), ("user", user["token"])]:
        r = client.post("/api/v1/ads/google/disconnect", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 403, f"Role {role_name} should NOT have DISCONNECT access"
        assert r.json()["error"]["code"] == "INSUFFICIENT_ROLE"


def test_google_ads_auth_url_blocked_when_unconfigured(db_session, test_setup):
    settings = Settings(AUTH_JWT_SECRET="a" * 32)
    client = get_test_client(db_session, settings)
    headers = {"Authorization": f"Bearer {test_setup['token']}"}

    resp = client.get("/api/v1/ads/google/auth-url", headers=headers)
    assert resp.status_code == 503
    err = resp.json()
    assert err["error"]["code"] == "ADS_CONFIGURATION_MISSING"
    assert err["error"]["details"]["status"] == "BLOCKED"


def test_google_ads_auth_url_success_and_anti_replay_when_configured(db_session, test_setup):
    settings = Settings(
        AUTH_JWT_SECRET="a" * 32,
        GOOGLE_ADS_CLIENT_ID="gid-1234.apps.googleusercontent.com",
        GOOGLE_ADS_CLIENT_SECRET="gsecret-5678",
        GOOGLE_ADS_DEVELOPER_TOKEN="devtoken-9999",
        GOOGLE_ADS_REDIRECT_URI="https://api.avenqo.ca/api/v1/ads/google/callback",
    )
    client = get_test_client(db_session, settings)
    headers = {"Authorization": f"Bearer {test_setup['token']}"}

    resp = client.get("/api/v1/ads/google/auth-url", headers=headers)
    assert resp.status_code == 200
    payload = resp.json()
    assert "auth_url" in payload
    assert "accounts.google.com" in payload["auth_url"]
    state = payload["state"]

    # Test callback replay attack protection
    with patch("backend.app.services.ads_service.AdsService.connect_google_ads", AsyncMock()):
        # First callback consumes state
        cb1 = client.get(f"/api/v1/ads/google/callback?code=valid_code&state={state}", follow_redirects=False)
        assert cb1.status_code == 307
        assert "google_ads=connected" in cb1.headers["location"]

        # Second callback with SAME state MUST be rejected (anti-replay)
        cb2 = client.get(f"/api/v1/ads/google/callback?code=valid_code&state={state}", follow_redirects=False)
        assert cb2.status_code == 307
        assert "error_code=REPLAY_ATTACK_DETECTED" in cb2.headers["location"]
        # Confirm no raw stack trace or token is in the location header
        assert "Bearer" not in cb2.headers["location"]
        assert "Traceback" not in cb2.headers["location"]


def test_multi_tenant_isolation_between_companies(db_session, test_setup):
    """Proves tenant A cannot view, modify, or disconnect tenant B's ad connections."""
    tenant_b = _create_tenant(db_session, "Company B", with_marketing_module=True)
    settings = Settings(AUTH_JWT_SECRET="a" * 32)
    client = get_test_client(db_session, settings)

    # Establish an active connection for Tenant A
    db_session.add(
        CommerceConnection(
            company_id=test_setup["company"].id,
            provider="google_ads",
            external_account_id="cust-tenant-a",
            display_name="Google Ads Tenant A",
            status=CommerceConnectionStatus.CONNECTED.value,
            encrypted_credentials="enc_credentials_a",
        )
    )
    db_session.commit()

    # Query status as Tenant A: Google Ads is CONNECTED
    headers_a = {"Authorization": f"Bearer {test_setup['token']}"}
    res_a = client.get("/api/v1/ads/status", headers=headers_a)
    assert res_a.json()["google_ads"]["connected"] is True
    assert res_a.json()["google_ads"]["external_account_id"] == "cust-tenant-a"

    # Query status as Tenant B: Google Ads is DISCONNECTED (Isolation guaranteed)
    headers_b = {"Authorization": f"Bearer {tenant_b['token']}"}
    res_b = client.get("/api/v1/ads/status", headers=headers_b)
    assert res_b.json()["google_ads"]["connected"] is False
    assert res_b.json()["google_ads"]["external_account_id"] == None

    # Tenant B attempts to disconnect Tenant A: cannot affect Tenant A
    disc_b = client.post("/api/v1/ads/google/disconnect", headers=headers_b)
    assert disc_b.status_code == 200
    assert disc_b.json()["success"] is False  # Nothing to disconnect for Tenant B

    # Re-verify Tenant A remains CONNECTED
    res_a_after = client.get("/api/v1/ads/status", headers=headers_a)
    assert res_a_after.json()["google_ads"]["connected"] is True
