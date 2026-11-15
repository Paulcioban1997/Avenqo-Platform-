"""An invited employee joins the existing company and only receives the granted access."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from backend.app.config.settings import get_settings
from backend.app.core.permission_grants import decode_grants, grants_for_responsibility
from backend.app.core.security import create_access_token, generate_token, hash_password, hash_token, verify_password
from backend.app.database import get_db
from backend.app.dependencies.auth import get_account_notifier
from backend.app.models import (
    AuthSession,
    Base,
    BillingAccount,
    Company,
    CompanyMembership,
    CompanyStatus,
    EmployeeInvitation,
    EmployeeTask,
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


def test_employee_sees_the_same_company_sources_only_with_data_access(db_session, client: TestClient) -> None:
    company = _company(db_session, f"sources-{uuid4().hex[:8]}")
    owner = _owner(db_session, company)
    vice_invitation, vice_raw, _mail = _invite(
        db_session, owner, f"vice-{uuid4()}@example.com", UserRole.USER, "Vice-président"
    )
    desk_invitation, desk_raw, _mail = _invite(
        db_session, owner, f"desk-{uuid4()}@example.com", UserRole.USER, "Adjoint administratif"
    )
    del vice_invitation, desk_invitation
    vice = WorkspaceService(db_session, _Mail()).accept_invitation(vice_raw, "Lucia", "Sources", "Password123!")
    desk = WorkspaceService(db_session, _Mail()).accept_invitation(desk_raw, "Camille", "Desk", "Password123!")
    client.cookies.clear()
    owner_sources = client.get("/api/v1/datasets/sources", headers=_headers(db_session, owner))
    vice_sources = client.get("/api/v1/datasets/sources", headers=_headers(db_session, vice))
    desk_sources = client.get("/api/v1/datasets/sources", headers=_headers(db_session, desk))
    assert owner_sources.status_code == 200
    assert vice_sources.status_code == 200
    assert vice_sources.json() == owner_sources.json()
    assert desk_sources.status_code == 403


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
    duties = db_session.scalars(select(EmployeeTask).where(EmployeeTask.assignee_user_id == user.id)).all()
    assert {task.title for task in duties} == {
        "Accueillir les rendez-vous du jour",
        "Confirmer les horaires autorisés",
    }
    assert {task.company_id for task in duties} == {company.id}
    with pytest.raises(WorkspaceError):
        WorkspaceService(db_session, _Mail()).accept_invitation(raw, "Lucia", "Desk", "Password123!")


def test_existing_account_is_never_rewritten_by_an_invitation(db_session) -> None:
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
        job_title="Comptable",
        is_active=True,
    )
    db_session.add(existing)
    db_session.commit()
    original_hash = existing.password_hash
    with pytest.raises(WorkspaceError, match="déjà un accès"):
        _invite(db_session, owner, email, UserRole.ANALYST, "Adjoint administratif")
    db_session.refresh(existing)
    assert existing.password_hash == original_hash
    assert existing.permission_grants is None
    assert existing.job_title == "Comptable"
    assert db_session.scalar(select(func.count()).select_from(User).where(User.email == email)) == 1
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
    office = set(grants_for_responsibility("Adjoint administratif", UserRole.USER))
    assert office == {"tasks:own", "crm:appointments:read", "crm:appointments:write"}
    assert "accounting:read" not in office
    assert "billing:manage" not in office
    WorkspaceService(db_session, _Mail()).revoke_invitation(owner, revoked.id)
    with pytest.raises(WorkspaceError):
        WorkspaceService(db_session, _Mail()).accept_invitation(revoked_raw, "Theo", "Tech", "Password123!")


def test_existing_administrator_keeps_their_place_and_can_enter_with_the_new_password(db_session) -> None:
    company = _company(db_session, f"keep-{uuid4().hex[:8]}")
    owner = _owner(db_session, company)
    email = f"mircea-{uuid4()}@example.com"
    admin = User(
        company_id=company.id,
        first_name="Mircea",
        last_name="Cioban",
        email=email,
        password_hash=hash_password("Oldpassword1!"),
        role=UserRole.ADMIN,
        job_title="Vice-président",
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()
    with pytest.raises(WorkspaceError, match="déjà un accès"):
        _invite(db_session, owner, email, UserRole.USER, "Adjoint administratif")
    raw = generate_token()
    db_session.add(EmployeeInvitation(
        company_id=company.id,
        invited_by_user_id=owner.id,
        email=email,
        role="user",
        job_title="Adjoint administratif",
        department="Administration",
        token_hash=hash_token(raw),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
    ))
    db_session.commit()
    with pytest.raises(WorkspaceError, match="appartient déjà"):
        WorkspaceService(db_session, _Mail()).accept_invitation(raw, "Lucia", "Cioban", "Newpassword1!")
    assert admin.first_name == "Mircea"
    assert admin.role == UserRole.ADMIN
    assert admin.job_title == "Vice-président"
    assert admin.permission_grants is None
    assert verify_password("Oldpassword1!", admin.password_hash)
    assert not verify_password("Newpassword1!", admin.password_hash)
    assert db_session.scalar(select(func.count()).select_from(User).where(User.email == email)) == 1


def _denied(response) -> bool:
    payload = response.json()
    if not isinstance(payload, dict):
        return False
    message = payload.get("error", {}).get("message", "")
    return response.status_code == 403 and ("pas accès" in message or "do not have access" in message)


def test_access_code_opens_only_the_inviting_company(db_session) -> None:
    company = _company(db_session, f"home-{uuid4().hex[:8]}")
    other = _company(db_session, f"away-{uuid4().hex[:8]}")
    owner = _owner(db_session, company)
    outsider = _owner(db_session, other)
    companies = db_session.scalar(select(func.count()).select_from(Company))
    accounts = db_session.scalar(select(func.count()).select_from(BillingAccount))
    email = f"lucia-{uuid4()}@example.com"
    invitation, _token, _mail = _invite(db_session, owner, email, UserRole.USER, "Adjoint administratif")
    service = WorkspaceService(db_session, _Mail())

    with pytest.raises(WorkspaceError):
        service.accept_invitation(None, "Lucia", "Cioban", "Password123!", code=invitation._raw_code, email=outsider.email)
    expired, _raw, _mail = _invite(db_session, owner, f"old-{uuid4()}@example.com", UserRole.USER, "Adjoint administratif")
    expired.expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    db_session.commit()
    with pytest.raises(WorkspaceError):
        WorkspaceService(db_session, _Mail()).accept_invitation(
            None, "Old", "Code", "Password123!", code=expired._raw_code, email=expired.email
        )

    guessed, _raw, _mail = _invite(db_session, owner, f"guess-{uuid4()}@example.com", UserRole.USER, "Adjoint administratif")
    for _attempt in range(5):
        with pytest.raises(WorkspaceError):
            WorkspaceService(db_session, _Mail()).preview_invitation(code="00000000", email=guessed.email)
    db_session.refresh(guessed)
    assert guessed.revoked_at is not None
    with pytest.raises(WorkspaceError):
        WorkspaceService(db_session, _Mail()).accept_invitation(
            None, "Guess", "Limit", "Password123!", code=guessed._raw_code, email=guessed.email
        )

    user = WorkspaceService(db_session, _Mail()).accept_invitation(
        None, "Lucia", "Cioban", "Password123!", code=invitation._raw_code, email=email
    )
    assert user.company_id == company.id
    assert user.email == email
    assert db_session.scalar(select(func.count()).select_from(Company)) == companies
    assert db_session.scalar(select(func.count()).select_from(BillingAccount)) == accounts
    with pytest.raises(WorkspaceError):
        WorkspaceService(db_session, _Mail()).accept_invitation(
            None, "Lucia", "Cioban", "Otherpass123!", code=invitation._raw_code, email=email
        )
    assert verify_password("Password123!", user.password_hash)
    assert not verify_password("Otherpass123!", user.password_hash)

    shared = f"shared-{uuid4()}@example.com"
    home_invite, _raw, _mail = _invite(db_session, owner, shared, UserRole.USER, "Adjoint administratif")
    away_invite, _raw, _mail = _invite(db_session, outsider, shared, UserRole.ANALYST, "Comptable")
    opened = WorkspaceService(db_session, _Mail()).accept_invitation(
        None, "Ada", "Join", "Password123!", code=home_invite._raw_code, email=shared
    )
    assert opened.company_id == company.id
    assert "accounting:read" not in set(decode_grants(opened.permission_grants) or ())
    with pytest.raises(WorkspaceError, match="autre entreprise"):
        WorkspaceService(db_session, _Mail()).accept_invitation(
            None, "Ada", "Join", "Otherpass123!", code=away_invite._raw_code, email=shared
        )
    db_session.refresh(opened)
    assert opened.company_id == company.id
    assert opened.job_title == "Adjoint administratif"
    assert verify_password("Password123!", opened.password_hash)
    db_session.refresh(away_invite)
    assert away_invite.accepted_at is None


def test_distinct_adjoint_keeps_agenda_tasks_and_the_same_login(db_session, client: TestClient) -> None:
    company = _company(db_session, f"desk-{uuid4().hex[:8]}")
    owner = _owner(db_session, company)
    colleague = User(
        company_id=company.id,
        first_name="Mircea",
        last_name="Cioban",
        email=f"mircea-{uuid4()}@example.com",
        password_hash=hash_password("Oldpassword1!"),
        role=UserRole.ADMIN,
        job_title="Vice-président",
        is_active=True,
    )
    db_session.add(colleague)
    db_session.commit()
    colleague_hash = colleague.password_hash
    email = f"lucia-{uuid4()}@example.com"
    invitation, _token, _mail = _invite(db_session, owner, email, UserRole.USER, "Adjoint administratif")
    preview = WorkspaceService(db_session, _Mail()).preview_invitation(code=invitation._raw_code, email=email)
    assert preview["company_name"] == company.name
    assert preview["job_title"] == "Adjoint administratif"
    assert preview["already_member"] == ""

    user = WorkspaceService(db_session, _Mail()).accept_invitation(
        None, "Lucia", "Cioban", "Password123!", code=invitation._raw_code, email=email
    )
    db_session.refresh(colleague)
    assert colleague.password_hash == colleague_hash
    assert colleague.role == UserRole.ADMIN
    assert colleague.job_title == "Vice-président"
    WorkspaceService(db_session, _Mail()).create_task(
        owner, assignee_user_id=owner.id, title="Dossier réservé au propriétaire", description=None, priority="medium", due_at=None
    )
    client.cookies.clear()
    signed_in = client.post("/api/v1/auth/login", json={"email": email, "password": "Password123!"})
    assert signed_in.status_code == 200
    body = signed_in.json()
    assert body["user"]["company_id"] == str(company.id)
    assert body["company"]["name"] == company.name
    permissions = set(body["user"]["permissions"])
    assert permissions == {"tasks:own", "crm:appointments:read", "crm:appointments:write"}
    again = client.post("/api/v1/auth/login", json={"email": email, "password": "Password123!"})
    assert again.status_code == 200
    assert set(again.json()["user"]["permissions"]) == permissions
    assert again.json()["user"]["company_id"] == str(company.id)
    client.cookies.clear()
    headers = {"Authorization": f"Bearer {again.json()['access_token']}", "X-Requested-With": "avenqo-web"}
    assert _denied(client.get("/api/v1/accounting/overview", headers=headers))
    assert _denied(client.get("/api/v1/billing/invoices", headers=headers))
    assert not _denied(client.get("/api/v1/crm/appointments", headers=headers))
    tasks = client.get("/api/v1/workspace/tasks", headers=headers)
    assert tasks.status_code == 200
    titles = {row["title"] for row in tasks.json()}
    assert titles == {
        "Tenir l'agenda et les suivis du bureau",
        "Préparer les documents demandés par la direction",
        "Classer les dossiers du service",
    }
    EmployeeService(db_session, _Mail()).update(owner, user.id, EmployeeUpdateRequest(is_active=False))
    assert client.get("/api/v1/workspace/guidance", headers=headers).status_code == 401
    client.cookies.clear()
    blocked = client.post("/api/v1/auth/login", json={"email": email, "password": "Password123!"})
    assert blocked.status_code == 401


def test_owner_corrects_one_address_without_moving_another_account(db_session, client: TestClient) -> None:
    company = _company(db_session, f"ero-{uuid4().hex[:8]}")
    other = _company(db_session, f"other-{uuid4().hex[:8]}")
    owner = _owner(db_session, company)
    outsider = _owner(db_session, other)
    outsider_hash = outsider.password_hash
    old_email = f"lucia-{uuid4()}@example.com"
    new_email = f"mircea-{uuid4()}@example.com"
    vice = User(
        company_id=company.id,
        first_name="Mircea",
        last_name="Cioban",
        email=old_email,
        password_hash=hash_password("Oldpassword1!"),
        role=UserRole.ADMIN,
        job_title="Vice-président",
        is_active=True,
        email_verified_at=datetime.now(timezone.utc),
    )
    admin = User(
        company_id=company.id,
        first_name="Ada",
        last_name="Admin",
        email=f"ada-{uuid4()}@example.com",
        password_hash=hash_password("Oldpassword1!"),
        role=UserRole.ADMIN,
        job_title="Adjointe",
        is_active=True,
    )
    db_session.add_all([vice, admin])
    db_session.flush()
    db_session.add(CompanyMembership(user_id=vice.id, company_id=company.id, role=UserRole.ADMIN, is_active=True))
    pending = EmployeeInvitation(
        company_id=company.id,
        invited_by_user_id=owner.id,
        email=old_email,
        role="user",
        job_title="Adjoint administratif",
        department="Administration",
        token_hash=hash_token(generate_token()),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=4),
    )
    db_session.add(pending)
    db_session.commit()
    password_hash = vice.password_hash
    service = WorkspaceService(db_session, _Mail())
    release = service.request_email_correction(owner, vice.id, outsider.email)
    assert release.releasing_user_id == outsider.id
    with pytest.raises(WorkspaceError, match="remplacement"):
        service.confirm_email_correction(code=release._raw_code, email=outsider.email)
    db_session.refresh(vice)
    db_session.refresh(outsider)
    assert vice.email == old_email
    assert outsider.password_hash == outsider_hash
    with pytest.raises(WorkspaceError, match="propriétaire"):
        service.request_email_correction(admin, vice.id, new_email)
    db_session.refresh(outsider)
    db_session.refresh(vice)
    assert outsider.email != new_email
    assert outsider.company_id == other.id
    assert outsider.role == UserRole.OWNER
    assert outsider.password_hash == outsider_hash
    assert vice.email == old_email
    assert vice.password_hash == password_hash

    correction = service.request_email_correction(owner, vice.id, new_email)
    db_session.refresh(vice)
    assert vice.email == old_email
    assert vice.job_title == "Vice-président"
    assert vice.role == UserRole.ADMIN
    for _attempt in range(5):
        with pytest.raises(WorkspaceError):
            service.confirm_email_correction(code="00000000", email=new_email)
    db_session.refresh(correction)
    assert correction.revoked_at is not None
    assert vice.email == old_email

    replacement = service.request_email_correction(owner, vice.id, new_email)
    confirmed, reissued = service.confirm_email_correction(code=replacement._raw_code, email=new_email)
    assert reissued is not None and reissued.job_title == "Adjoint administratif"
    db_session.refresh(vice)
    assert confirmed.id == vice.id
    assert vice.email == new_email
    assert vice.company_id == company.id
    assert vice.role == UserRole.ADMIN
    assert vice.job_title == "Vice-président"
    assert vice.permission_grants is None
    assert vice.password_hash == password_hash
    assert vice.first_name == "Mircea"
    db_session.refresh(pending)
    assert pending.revoked_at is not None
    with pytest.raises(WorkspaceError):
        service.confirm_email_correction(token=replacement._raw_token)
    db_session.refresh(outsider)
    assert outsider.company_id == other.id
    assert outsider.password_hash == outsider_hash

    assert reissued.company_id == company.id
    grants = set(decode_grants(reissued.permission_grants) or ())
    assert "billing:manage" not in grants
    assert "accounting:read" not in grants
    assert "crm:appointments:read" in grants
    lucia = service.accept_invitation(
        None, "Lucia", "Cioban", "Password123!", code=reissued._raw_code, email=old_email
    )
    assert lucia.id != vice.id
    assert lucia.company_id == company.id
    assert lucia.email == old_email
    db_session.refresh(vice)
    assert vice.email == new_email
    assert vice.password_hash == password_hash

    client.cookies.clear()
    vice_login = client.post("/api/v1/auth/login", json={"email": new_email, "password": "Oldpassword1!"})
    lucia_login = client.post("/api/v1/auth/login", json={"email": old_email, "password": "Password123!"})
    assert vice_login.status_code == 200
    assert lucia_login.status_code == 200
    assert vice_login.json()["user"]["company_id"] == lucia_login.json()["user"]["company_id"] == str(company.id)
    assert vice_login.json()["user"]["id"] != lucia_login.json()["user"]["id"]
    assert "users:manage" in vice_login.json()["user"]["permissions"]
    assert set(lucia_login.json()["user"]["permissions"]) == {
        "tasks:own",
        "crm:appointments:read",
        "crm:appointments:write",
    }
    client.cookies.clear()
    headers = {"Authorization": f"Bearer {lucia_login.json()['access_token']}", "X-Requested-With": "avenqo-web"}
    assert _denied(client.get("/api/v1/accounting/overview", headers=headers))
    assert _denied(client.get("/api/v1/billing/invoices", headers=headers))


def test_inbox_can_release_its_address_without_moving_either_company(db_session, client: TestClient) -> None:
    company = _company(db_session, f"home-{uuid4().hex[:8]}")
    other = _company(db_session, f"away-{uuid4().hex[:8]}")
    owner = _owner(db_session, company)
    holder = _owner(db_session, other)
    holder.email_verified_at = datetime.now(timezone.utc)
    db_session.commit()
    held_email = holder.email
    held_hash = holder.password_hash
    vice = User(
        company_id=company.id,
        first_name="Mircea",
        last_name="Cioban",
        email=f"vice-{uuid4()}@example.com",
        password_hash=hash_password("Oldpassword1!"),
        role=UserRole.ADMIN,
        job_title="Vice-président",
        is_active=True,
        email_verified_at=datetime.now(timezone.utc),
    )
    colleague = User(
        company_id=company.id,
        first_name="Luc",
        last_name="Same",
        email=f"same-{uuid4()}@example.com",
        password_hash=hash_password("Oldpassword1!"),
        role=UserRole.USER,
        job_title="Comptable",
        is_active=True,
    )
    db_session.add_all([vice, colleague])
    db_session.commit()
    vice_hash = vice.password_hash
    service = WorkspaceService(db_session, _Mail())
    with pytest.raises(WorkspaceError, match="dans cette entreprise"):
        service.request_email_correction(owner, vice.id, colleague.email)
    correction = service.request_email_correction(owner, vice.id, held_email)
    replacement = f"released-{uuid4()}@example.com"
    service.confirm_email_correction(
        code=correction._raw_code,
        email=held_email,
        replacement_email=replacement,
    )
    db_session.refresh(vice)
    db_session.refresh(holder)
    assert vice.email == held_email
    assert vice.company_id == company.id
    assert vice.role == UserRole.ADMIN
    assert vice.job_title == "Vice-président"
    assert vice.password_hash == vice_hash
    assert holder.email == replacement
    assert holder.company_id == other.id
    assert holder.role == UserRole.OWNER
    assert holder.password_hash == held_hash
    client.cookies.clear()
    vice_login = client.post("/api/v1/auth/login", json={"email": held_email, "password": "Oldpassword1!"})
    holder_login = client.post("/api/v1/auth/login", json={"email": replacement, "password": "Ownerpass1!"})
    assert vice_login.status_code == 200
    assert holder_login.status_code == 200
    assert vice_login.json()["user"]["company_id"] == str(company.id)
    assert holder_login.json()["user"]["company_id"] == str(other.id)
