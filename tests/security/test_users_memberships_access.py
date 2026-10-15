"""Access-path tests for ``users`` and ``company_memberships``.

These two tables carry ``company_id`` but intentionally have NO PostgreSQL RLS
(login and tenant switching must read them before a tenant GUC exists, see
``backend/app/services/tenant_rls.py``). Their isolation therefore rests on the
application layer, which these tests exercise (SQLite, synthetic data).

Scope limits (kept honest): the Central AI check is a static inventory of tool
names, not a runtime tool call; no PostgreSQL role is involved here.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.config.settings import get_settings
from backend.app.core.permissions import permissions_for
from backend.app.core.security import create_access_token
from backend.app.database import get_db
from backend.app.dependencies.auth import get_account_notifier
from backend.app.models import AuthSession, Base, Company, CompanyMembership, CompanyStatus, User, UserRole
from backend.main import create_application
from tests.subscription_helpers import add_active_subscription

ROOT = Path(__file__).resolve().parents[2]


class _NullNotifier:
    def send_email_verification(self, email: str, token: str) -> None:
        pass

    def send_password_reset(self, email: str, token: str) -> None:
        pass


@pytest.fixture
def db_session(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'users-memberships.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        yield session


@pytest.fixture
def client(db_session, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AUTH_JWT_SECRET", "a" * 32)
    get_settings.cache_clear()
    app = create_application()

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_account_notifier] = lambda: _NullNotifier()
    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()


def _company(session, slug: str, *, status: CompanyStatus = CompanyStatus.ACTIVE) -> Company:
    company = Company(
        name=f"Co {slug}", slug=slug, email=f"{slug}@example.com", country="CA",
        timezone="America/Toronto", industry="Retail", subscription_plan="professional",
        status=status,
    )
    session.add(company)
    session.flush()
    add_active_subscription(session, company)
    return company


def _user(session, company: Company, *, role: UserRole = UserRole.OWNER, tag: str = "u") -> User:
    user = User(
        company_id=company.id, first_name="Syn", last_name=tag,
        email=f"{tag}-{uuid4()}@example.com", password_hash="hash", role=role,
    )
    session.add(user)
    session.flush()
    session.add(CompanyMembership(user_id=user.id, company_id=company.id, role=role, is_active=True))
    session.flush()
    return user


def _headers(session, user: User) -> dict[str, str]:
    session_id = uuid4()
    now = datetime.now(timezone.utc)
    session.add(AuthSession(
        id=session_id, user_id=user.id, token_hash=f"hash-{session_id}",
        created_at=now, expires_at=now + timedelta(days=1),
    ))
    session.commit()
    token, _ = create_access_token(user.id, user.company_id, session_id)
    return {"Authorization": f"Bearer {token}", "X-Requested-With": "avenqo-web"}


def test_employee_list_never_contains_foreign_users(db_session, client: TestClient) -> None:
    company_a, company_b = _company(db_session, "um-list-a"), _company(db_session, "um-list-b")
    owner_a = _user(db_session, company_a, tag="a-owner")
    foreign = _user(db_session, company_b, tag="b-owner")
    db_session.commit()

    response = client.get("/api/v1/employees", headers=_headers(db_session, owner_a))
    assert response.status_code == 200
    emails = {row["email"] for row in response.json()}
    assert owner_a.email in emails
    assert foreign.email not in emails
    assert foreign.email not in response.text


def test_owner_cannot_modify_foreign_employee_by_id(db_session, client: TestClient) -> None:
    company_a, company_b = _company(db_session, "um-patch-a"), _company(db_session, "um-patch-b")
    owner_a = _user(db_session, company_a, tag="a-owner")
    victim = _user(db_session, company_b, role=UserRole.VIEWER, tag="b-viewer")
    db_session.commit()

    response = client.patch(
        f"/api/v1/employees/{victim.id}",
        json={"role": "manager", "is_active": False},
        headers=_headers(db_session, owner_a),
    )
    assert response.status_code == 404
    db_session.refresh(victim)
    assert victim.role == UserRole.VIEWER
    assert victim.is_active is True
    assert victim.company_id == company_b.id


def test_switch_tenant_without_membership_is_refused(db_session, client: TestClient) -> None:
    company_a, company_b = _company(db_session, "um-sw-a"), _company(db_session, "um-sw-b")
    user_a = _user(db_session, company_a, tag="a-owner")
    db_session.commit()

    response = client.post(
        "/api/v1/auth/switch-tenant", json={"company_id": str(company_b.id)},
        headers=_headers(db_session, user_a),
    )
    assert response.status_code == 403
    db_session.refresh(user_a)
    assert user_a.company_id == company_a.id
    assert db_session.scalar(select(CompanyMembership).where(
        CompanyMembership.user_id == user_a.id, CompanyMembership.company_id == company_b.id,
    )) is None


def test_switch_tenant_with_deactivated_membership_is_refused(db_session, client: TestClient) -> None:
    company_a, company_b = _company(db_session, "um-sw2-a"), _company(db_session, "um-sw2-b")
    user_a = _user(db_session, company_a, tag="a-owner")
    db_session.add(CompanyMembership(user_id=user_a.id, company_id=company_b.id, role=UserRole.ADMIN, is_active=False))
    db_session.commit()

    response = client.post(
        "/api/v1/auth/switch-tenant", json={"company_id": str(company_b.id)},
        headers=_headers(db_session, user_a),
    )
    assert response.status_code == 403
    db_session.refresh(user_a)
    assert user_a.company_id == company_a.id


def test_switch_tenant_does_not_reveal_status_of_foreign_company(db_session, client: TestClient) -> None:
    """A non-member must get the same answer for an active and a suspended company."""
    company_a = _company(db_session, "um-leak-a")
    active_b = _company(db_session, "um-leak-b-active")
    suspended_b = _company(db_session, "um-leak-b-susp", status=CompanyStatus.SUSPENDED)
    user_a = _user(db_session, company_a, tag="a-owner")
    db_session.commit()
    headers = _headers(db_session, user_a)

    active = client.post("/api/v1/auth/switch-tenant", json={"company_id": str(active_b.id)}, headers=headers)
    suspended = client.post("/api/v1/auth/switch-tenant", json={"company_id": str(suspended_b.id)}, headers=headers)
    assert active.status_code == suspended.status_code == 403
    def _strip_request_id(payload: dict) -> dict:
        return {k: v for k, v in payload.items() if k != "request_id"}
    assert _strip_request_id(active.json()) == _strip_request_id(suspended.json())


def test_switch_tenant_role_is_taken_from_target_membership(db_session, client: TestClient) -> None:
    company_a, company_b = _company(db_session, "um-role-a"), _company(db_session, "um-role-b")
    user_a = _user(db_session, company_a, role=UserRole.OWNER, tag="a-owner")
    db_session.add(CompanyMembership(user_id=user_a.id, company_id=company_b.id, role=UserRole.VIEWER, is_active=True))
    db_session.commit()

    response = client.post(
        "/api/v1/auth/switch-tenant", json={"company_id": str(company_b.id)},
        headers=_headers(db_session, user_a),
    )
    assert response.status_code == 200
    db_session.refresh(user_a)
    assert user_a.company_id == company_b.id
    assert user_a.role == UserRole.VIEWER  # owner rights in A must not follow into B


def test_demoting_an_employee_revokes_membership_permissions(db_session, client: TestClient) -> None:
    """Permissions for AI/Voice/CRM are derived from CompanyMembership.role."""
    company = _company(db_session, "um-demote")
    owner = _user(db_session, company, role=UserRole.OWNER, tag="owner")
    admin = _user(db_session, company, role=UserRole.ADMIN, tag="admin")
    db_session.commit()

    response = client.patch(
        f"/api/v1/employees/{admin.id}", json={"role": "viewer"},
        headers=_headers(db_session, owner),
    )
    assert response.status_code == 200
    membership = db_session.scalar(select(CompanyMembership).where(
        CompanyMembership.user_id == admin.id, CompanyMembership.company_id == company.id,
    ))
    db_session.refresh(membership)
    assert membership.role == UserRole.VIEWER
    assert "ai:use" not in permissions_for(membership.role)
    assert "users:manage" not in permissions_for(membership.role)


def test_deactivating_an_employee_deactivates_membership(db_session, client: TestClient) -> None:
    company = _company(db_session, "um-deactivate")
    owner = _user(db_session, company, role=UserRole.OWNER, tag="owner")
    member = _user(db_session, company, role=UserRole.MANAGER, tag="manager")
    db_session.commit()

    response = client.patch(
        f"/api/v1/employees/{member.id}", json={"is_active": False},
        headers=_headers(db_session, owner),
    )
    assert response.status_code == 200
    membership = db_session.scalar(select(CompanyMembership).where(
        CompanyMembership.user_id == member.id, CompanyMembership.company_id == company.id,
    ))
    db_session.refresh(membership)
    assert membership.is_active is False


def test_central_ai_tool_inventory_exposes_no_user_or_membership_tool() -> None:
    """Static inventory of declared tool names (not a runtime tool call)."""
    pattern = re.compile(r'^\s+name\s*=\s*"([a-z_]+)"', re.MULTILINE)
    names: list[str] = []
    for path in (ROOT / "backend" / "app" / "ai" / "tools").rglob("*_tools.py"):
        names += pattern.findall(path.read_text(encoding="utf-8"))
    assert names, "tool inventory unexpectedly empty"
    forbidden = re.compile(r"user|member|employee|staff|password|session|credential|token|secret")
    offenders = [name for name in names if forbidden.search(name)]
    assert offenders == [], f"Central AI tools touching identity data: {offenders}"
