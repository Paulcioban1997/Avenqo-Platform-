"""An invited employee joins the existing company and only receives the granted access."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from backend.app.config.settings import get_settings
from backend.app.core.permission_grants import decode_grants
from backend.app.core.security import create_access_token, hash_password
from backend.app.database import get_db
from backend.app.dependencies.auth import get_account_notifier
from backend.app.models import (
    AuthSession,
    Base,
    BillingAccount,
    Company,
    CompanyMembership,
    CompanyStatus,
    User,
    UserRole,
)
from backend.app.schemas.employees import EmployeeUpdateRequest
from backend.app.services.employee_service import EmployeeService
from backend.app.services.workspace_service import WorkspaceError, WorkspaceService
from backend.main import create_application
from tests.subscription_helpers import add_active_subscription


class _Mail:
    email_delivery_configured = True
    delivers_to_mailbox = True
    test_transport = True

    def __init__(self) -> None:
        self.body = ""

    def send_transactional(self, recipient: str, subject: str, body: str, html_body: str | None = None) -> None:
        self.body = body

    def send_email_verification(self, email: str, token: str) -> None:
        return None


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'team.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        yield session


@pytest.fixture
def client(db_session, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AUTH_JWT_SECRET", "b" * 32)
    get_settings.cache_clear()
    app = create_application()

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_account_notifier] = lambda: _Mail()
    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()


def _company(session, slug: str) -> Company:
    company = Company(
        name=f"Clinique {slug}",
        slug=slug,
        email=f"{slug}@example.com",
        country="CA",
        timezone="America/Toronto",
        industry="Health",
        subscription_plan="professional",
        status=CompanyStatus.ACTIVE,
    )
    session.add(company)
    session.flush()
    add_active_subscription(session, company)
    return company


def _owner(session, company: Company) -> User:
    user = User(
        company_id=company.id,
        first_name="Francis",
        last_name="Owner",
        email=f"owner-{uuid4()}@example.com",
        password_hash=hash_password("Ownerpass1!"),
        role=UserRole.OWNER,
        is_active=True,
    )
    session.add(user)
    session.flush()
    session.add(CompanyMembership(user_id=user.id, company_id=company.id, role=UserRole.OWNER, is_active=True))
    session.commit()
    return user


def _headers(session, user: User) -> dict[str, str]:
    session_id = uuid4()
    now = datetime.now(timezone.utc)
    session.add(AuthSession(
        id=session_id,
        user_id=user.id,
        token_hash=f"hash-{session_id}",
        created_at=now,
        expires_at=now + timedelta(days=1),
    ))
    session.commit()
    token, _ = create_access_token(user.id, user.company_id, session_id)
    return {"Authorization": f"Bearer {token}", "X-Requested-With": "avenqo-web"}


def _invite(session, owner: User, email: str, role: UserRole, title: str):
    mail = _Mail()
    invitation = WorkspaceService(session, mail).invite(owner, email, role, title, "Accueil")
    return invitation, invitation._raw_token, mail


def test_new_employee_joins_the_existing_company_with_limited_access(db_session) -> None:
    company = _company(db_session, f"join-{uuid4().hex[:8]}")
    owner = _owner(db_session, company)
    companies = db_session.scalar(select(func.count()).select_from(Company))
    accounts = db_session.scalar(select(func.count()).select_from(BillingAccount))
    invitation, raw, _mail = _invite(
        db_session, owner, f"desk-{uuid4()}@example.com", UserRole.USER, "Réceptionniste"
    )
    preview = WorkspaceService(db_session, _Mail()).preview_invitation(raw)
    assert preview["company_name"] == company.name
    assert preview["job_title"] == "Réceptionniste"
    assert invitation.accepted_at is None

    user = WorkspaceService(db_session, _Mail()).accept_invitation(raw, "Lucia", "Desk", "Password123!")
    assert user.company_id == company.id
    assert db_session.scalar(select(func.count()).select_from(Company)) == companies
    assert db_session.scalar(select(func.count()).select_from(BillingAccount)) == accounts
    membership = db_session.scalar(select(CompanyMembership).where(CompanyMembership.user_id == user.id))
    assert membership is not None and membership.company_id == company.id and membership.is_active
    grants = set(decode_grants(user.permission_grants) or ())
    assert "crm:appointments:read" in grants
    assert "accounting:read" not in grants
    assert "billing:manage" not in grants
    assert "company:manage" not in grants
    with pytest.raises(WorkspaceError):
        WorkspaceService(db_session, _Mail()).accept_invitation(raw, "Lucia", "Desk", "Password123!")


def test_existing_same_company_account_is_reused_and_other_company_is_refused(db_session) -> None:
    company = _company(db_session, f"same-{uuid4().hex[:8]}")
    other = _company(db_session, f"other-{uuid4().hex[:8]}")
    owner = _owner(db_session, company)
    email = f"book-{uuid4()}@example.com"
    existing = User(
        company_id=company.id,
        first_name="Camille",
        last_name="Books",
        email=email,
        password_hash=hash_password("Password123!"),
        role=UserRole.USER,
        is_active=True,
    )
    db_session.add(existing)
    db_session.commit()
    _invitation, raw, _mail = _invite(db_session, owner, email, UserRole.ANALYST, "Comptable")
    users_before = db_session.scalar(select(func.count()).select_from(User))
    joined = WorkspaceService(db_session, _Mail()).accept_invitation(raw, "Camille", "Books", "Password123!")
    assert joined.id == existing.id
    assert db_session.scalar(select(func.count()).select_from(User)) == users_before
    assert "accounting:write" in set(decode_grants(joined.permission_grants) or ())
    with pytest.raises(WorkspaceError, match="autre entreprise"):
        _invite(db_session, owner, _owner(db_session, other).email, UserRole.USER, "Réceptionniste")


def test_title_cannot_grant_more_access_than_the_inviter(db_session) -> None:
    company = _company(db_session, f"cap-{uuid4().hex[:8]}")
    owner = _owner(db_session, company)
    admin = User(
        company_id=company.id,
        first_name="Ada",
        last_name="Admin",
        email=f"admin-{uuid4()}@example.com",
        password_hash=hash_password("Password123!"),
        role=UserRole.ADMIN,
        is_active=True,
    )
    manager = User(
        company_id=company.id,
        first_name="Max",
        last_name="Manager",
        email=f"manager-{uuid4()}@example.com",
        password_hash=hash_password("Password123!"),
        role=UserRole.MANAGER,
        is_active=True,
    )
    db_session.add_all([admin, manager])
    db_session.commit()
    invitation, _raw, _mail = _invite(db_session, admin, f"books-{uuid4()}@example.com", UserRole.ANALYST, "Comptable")
    grants = set(decode_grants(invitation.permission_grants) or ())
    assert "accounting:write" not in grants
    assert "billing:manage" not in grants
    with pytest.raises(WorkspaceError):
        _invite(db_session, manager, f"nope-{uuid4()}@example.com", UserRole.USER, "Réceptionniste")
    with pytest.raises(WorkspaceError):
        _invite(db_session, owner, f"owner-{uuid4()}@example.com", UserRole.OWNER, "Propriétaire")
    marketing, _token, _mail = _invite(
        db_session, owner, f"market-{uuid4()}@example.com", UserRole.MANAGER, "Responsable marketing"
    )
    market_grants = set(decode_grants(marketing.permission_grants) or ())
    assert "marketing:read" in market_grants
    assert "data:manage" not in market_grants
    assert "accounting:read" not in market_grants


def test_expired_revoked_and_removed_access_stop_at_the_server(db_session, client: TestClient) -> None:
    company = _company(db_session, f"guard-{uuid4().hex[:8]}")
    owner = _owner(db_session, company)
    invitation, raw, _mail = _invite(
        db_session, owner, f"desk-{uuid4()}@example.com", UserRole.USER, "Réceptionniste"
    )
    invitation.expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    db_session.commit()
    with pytest.raises(WorkspaceError):
        WorkspaceService(db_session, _Mail()).accept_invitation(raw, "Luc", "Desk", "Password123!")

    fresh, fresh_raw, _mail = _invite(
        db_session, owner, f"live-{uuid4()}@example.com", UserRole.USER, "Réceptionniste"
    )
    response = client.post(
        "/api/v1/workspace/invitations/accept",
        json={
            "token": fresh_raw,
            "first_name": "Luc",
            "last_name": "Desk",
            "password": "Password123!",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["company_name"] == company.name
    assert body["home"] == "/employees"
    employee = db_session.scalar(select(User).where(User.email == fresh.email))
    assert employee is not None
    headers = _headers(db_session, employee)
    accounting = client.get("/api/v1/accounting/overview", headers=headers)
    clients = client.get("/api/v1/crm/clients", headers=headers)
    appointments = client.get("/api/v1/crm/appointments", headers=headers)
    dashboard = client.get("/api/v1/dashboard", headers=headers)
    def denied(response) -> bool:
        payload = response.json()
        if not isinstance(payload, dict):
            return False
        message = payload.get("error", {}).get("message", "")
        return response.status_code == 403 and ("pas accès" in message or "do not have access" in message)

    assert denied(accounting)
    assert denied(clients)
    assert not denied(appointments)
    assert denied(dashboard)

    EmployeeService(db_session, _Mail()).update(owner, employee.id, EmployeeUpdateRequest(is_active=False))
    removed = client.get("/api/v1/workspace/guidance", headers=headers)
    assert removed.status_code == 401

    revoked, revoked_raw, _mail = _invite(
        db_session, owner, f"later-{uuid4()}@example.com", UserRole.USER, "Technicien de service"
    )
    WorkspaceService(db_session, _Mail()).revoke_invitation(owner, revoked.id)
    with pytest.raises(WorkspaceError):
        WorkspaceService(db_session, _Mail()).accept_invitation(revoked_raw, "Theo", "Tech", "Password123!")
