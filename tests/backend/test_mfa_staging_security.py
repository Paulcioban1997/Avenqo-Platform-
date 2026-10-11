"""Regressions for active MFA enrollment and tenant identity binding."""
from uuid import UUID

from backend.app.models import User
from backend.app.services.totp import totp_code
from tests.backend.test_auth import auth_environment
from tests.backend.test_security_center import account, headers


def test_active_mfa_cannot_be_disabled_by_reenrollment(auth_environment):
    client, factory, notifier = auth_environment
    login = account(client, notifier, "mfa-staging@example.com", "MFA staging")
    request_headers = headers(login)
    enrollment = client.post("/api/v1/security/mfa/enroll", headers=request_headers)
    assert enrollment.status_code == 200
    secret = enrollment.json()["secret"]
    confirmed = client.post("/api/v1/security/mfa/confirm", headers=request_headers, json={"code":totp_code(secret)})
    assert confirmed.status_code == 200
    refused = client.post("/api/v1/security/mfa/enroll", headers=request_headers)
    assert refused.status_code == 409
    overview = client.get("/api/v1/security/overview", headers=request_headers)
    assert overview.json()["mfa_enabled"] is True
    with factory() as db:
        user = db.get(User, UUID(str(login["user"]["id"])))
        assert user.mfa_enabled


def test_identity_only_workspace_route_binds_verified_company(auth_environment, monkeypatch):
    client, factory, notifier = auth_environment
    login = account(client, notifier, "rls-staging@example.com", "RLS staging")
    observed = []
    monkeypatch.setattr("backend.app.services.tenant_rls.apply_tenant_rls", lambda db,cid,**options: observed.append((cid,options)))
    response = client.get("/api/v1/workspace/team", headers=headers(login))
    assert response.status_code == 200
    assert observed
    assert all(str(cid)==str(login["company"]["id"]) and not options["bypass"] for cid,options in observed)
