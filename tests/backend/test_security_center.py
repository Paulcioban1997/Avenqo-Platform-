"""Security center must stay available without billing and never cross tenants."""
from sqlalchemy import select
from datetime import datetime, timedelta, timezone
import pytest
from fastapi import HTTPException
from backend.app.dependencies.admin import get_admin_tenant_context
from backend.app.dependencies.auth import CurrentIdentity

from backend.app.models import AuditLogEntry, AuthSession, CompanyMembership, User, UserRole
from tests.backend.test_auth import auth_environment, registration_payload, verify_and_login


def account(client, notifier, email, name):
    assert client.post("/api/v1/auth/register", json=registration_payload(email, name)).status_code == 201
    return verify_and_login(client, notifier, email)


def headers(login):
    return {"Authorization": f"Bearer {login['access_token']}"}


def test_sessions_are_private_and_revocation_blocks_access_and_refresh(auth_environment):
    client, factory, notifier = auth_environment
    first = account(client, notifier, "first@example.ca", "First")
    other = account(client, notifier, "other@example.ca", "Other")
    own_sessions = client.get("/api/v1/security/sessions", headers=headers(first))
    assert own_sessions.status_code == 200
    assert own_sessions.json()
    assert all("token_hash" not in s for s in own_sessions.json())
    own_id = next(s["id"] for s in own_sessions.json() if s["current"])
    assert client.delete(f"/api/v1/security/sessions/{own_id}", headers=headers(other)).status_code == 404
    assert client.delete(f"/api/v1/security/sessions/{own_id}", headers=headers(first)).status_code == 204
    assert client.get("/api/v1/security/overview", headers=headers(first)).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}).status_code == 401
    logs = client.get("/api/v1/security/audit", headers=headers(other)).json()
    assert not logs


def test_audit_filters_tenant_redacts_metadata_and_enforces_role(auth_environment):
    client, factory, notifier = auth_environment
    first = account(client, notifier, "first@example.ca", "First")
    other = account(client, notifier, "other@example.ca", "Other")
    with factory() as db:
        user = db.scalar(select(User).where(User.email == "first@example.ca"))
        db.add(AuditLogEntry(actor_user_id=user.id, company_id=user.company_id, action="test_audit",
                             target_type="test", safe_metadata={"secret": "must-not-leak"}))
        db.commit()
    own = client.get("/api/v1/security/audit", headers=headers(first))
    assert own.status_code == 200 and len(own.json()) == 1
    assert "must-not-leak" not in own.text
    assert client.get("/api/v1/security/audit", headers=headers(other)).json() == []
    assert client.get("/api/v1/security/audit?limit=101", headers=headers(first)).status_code == 422
    with factory() as db:
        user = db.scalar(select(User).where(User.email == "first@example.ca"))
        user.role = UserRole.VIEWER
        db.commit()
    assert client.get("/api/v1/security/audit", headers=headers(first)).status_code == 403
    assert client.get("/api/v1/security/overview", headers=headers(first)).status_code == 200


def test_platform_admin_has_no_implicit_tenant_membership(auth_environment):
    client, factory, notifier = auth_environment
    first = account(client, notifier, "admin@example.ca", "Platform")
    other = account(client, notifier, "other@example.ca", "Other")
    with factory() as db:
        user = db.scalar(select(User).where(User.email == "admin@example.ca"))
        user.is_platform_admin = True
        db.commit()
    orgs = client.get("/api/v1/auth/organizations", headers=headers(first)).json()
    assert [o["id"] for o in orgs] == [first["company"]["id"]]
    assert client.post("/api/v1/auth/switch-tenant", headers=headers(first),
                       json={"company_id": other["company"]["id"]}).status_code == 403


def test_switch_rotates_cookies_revokes_previous_sessions_and_uses_membership_role(auth_environment):
    client, factory, notifier = auth_environment
    first = account(client, notifier, "first@example.ca", "First")
    other = account(client, notifier, "other@example.ca", "Other")
    with factory() as db:
        user = db.scalar(select(User).where(User.email == "first@example.ca"))
        target = db.scalar(select(User).where(User.email == "other@example.ca"))
        db.add(CompanyMembership(user_id=user.id, company_id=target.company_id, role=UserRole.VIEWER))
        db.commit()
    switched = client.post("/api/v1/auth/switch-tenant", headers=headers(first),
                           json={"company_id": other["company"]["id"]})
    assert switched.status_code == 200
    data = switched.json()
    assert data["user"]["role"] == "viewer"
    assert data["refresh_token"] != first["access_token"]
    assert client.cookies.get("avenqo_access_token") == data["access_token"]
    assert client.get("/api/v1/auth/me").json()["company"]["id"] == other["company"]["id"]
    client.cookies.clear()
    assert client.get("/api/v1/auth/me", headers=headers(first)).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}).status_code == 401
    assert client.get("/api/v1/security/audit", headers=headers(data)).status_code == 403
    refreshed = client.post("/api/v1/auth/refresh", json={"refresh_token": data["refresh_token"]})
    assert refreshed.status_code == 200
    returned = client.post("/api/v1/auth/switch-tenant", headers={"X-Requested-With": "avenqo-web"},
                           json={"company_id": first["company"]["id"]})
    assert returned.status_code == 200 and returned.json()["user"]["role"] == "owner"


def test_support_consent_is_scoped_expiring_revocable_and_owner_only(auth_environment):
    client, factory, notifier = auth_environment
    owner = account(client, notifier, "owner@example.ca", "Customer")
    support = account(client, notifier, "support@example.ca", "Support")
    with factory() as db:
        user = db.scalar(select(User).where(User.email == "support@example.ca"))
        user.is_platform_admin = True
        db.commit()
        auth_session = db.scalar(select(AuthSession).where(AuthSession.user_id == user.id,
                                                          AuthSession.revoked_at.is_(None)))
        identity = CurrentIdentity(auth_session, user, support["access_token"])
        company_id = db.scalar(select(User).where(User.email == "owner@example.ca")).company_id
        with pytest.raises(HTTPException) as denied:
            get_admin_tenant_context(company_id, identity, db)
        assert denied.value.status_code == 403
    grant = client.post("/api/v1/security/support-access", headers=headers(owner),
                        json={"recipient_email": "support@example.ca", "reason": "Diagnostiquer une synchronisation", "duration_minutes": 15})
    assert grant.status_code == 201 and grant.json()["scope"] == "retail:read"
    with factory() as db:
        user = db.scalar(select(User).where(User.email == "support@example.ca"))
        auth_session = db.scalar(select(AuthSession).where(AuthSession.user_id == user.id,
                                                          AuthSession.revoked_at.is_(None)))
        identity = CurrentIdentity(auth_session, user, support["access_token"])
        assert get_admin_tenant_context(company_id, identity, db).company_id == company_id
        row = db.scalar(select(AuditLogEntry).where(AuditLogEntry.action == "support_access_granted"))
        row.safe_metadata = {**row.safe_metadata, "expires_at": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()}
        db.commit()
        with pytest.raises(HTTPException):
            get_admin_tenant_context(company_id, identity, db)
    assert client.get("/api/v1/security/support-access", headers=headers(owner)).json() == []
    grant = client.post("/api/v1/security/support-access", headers=headers(owner),
                        json={"recipient_email": "support@example.ca", "reason": "Nouvelle autorisation de diagnostic"})
    grant_id = grant.json()["id"]
    assert client.delete(f"/api/v1/security/support-access/{grant_id}", headers=headers(support)).status_code == 404
    assert client.delete(f"/api/v1/security/support-access/{grant_id}", headers=headers(owner)).status_code == 204
    assert client.get("/api/v1/security/support-access", headers=headers(owner)).json() == []
    with factory() as db:
        user = db.scalar(select(User).where(User.email == "owner@example.ca"))
        user.role = UserRole.ADMIN
        db.commit()
    assert client.post("/api/v1/security/support-access", headers=headers(owner),
                       json={"recipient_email": "support@example.ca", "reason": "Diagnostiquer une synchronisation"}).status_code == 403
