"""Negative multi-tenant access: client headers and foreign IDs never leak data."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.ai.chat.conversation_service import ConversationService
from backend.app.config.settings import get_settings
from backend.app.core.security import create_access_token
from backend.app.core.tenant_execution import client_tenant_override, strip_client_tenant_arguments
from backend.app.database import get_db
from backend.app.dependencies.auth import get_account_notifier
from backend.app.models import AuthSession, Base, Company, CompanyMembership, User, UserRole
from backend.app.models.crm import CRMClient
from backend.main import create_application
from tests.subscription_helpers import add_active_subscription


class _NullNotifier:
    def send_email_verification(self, email: str, token: str) -> None:
        pass

    def send_password_reset(self, email: str, token: str) -> None:
        pass


@pytest.fixture
def db_session(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'cross-tenant.db'}")
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


def _company(session, *, slug: str) -> Company:
    company = Company(
        name=f"Co {slug}",
        slug=slug,
        email=f"{slug}@example.com",
        country="CA",
        timezone="America/Toronto",
        industry="Retail",
        subscription_plan="professional",
    )
    session.add(company)
    session.flush()
    add_active_subscription(session, company)
    return company


def _user(session, company: Company, *, role: UserRole = UserRole.OWNER) -> User:
    user = User(
        company_id=company.id,
        first_name="Ana",
        last_name="Lyst",
        email=f"user-{uuid4()}@example.com",
        password_hash="hash",
        role=role,
    )
    session.add(user)
    session.flush()
    session.add(CompanyMembership(user_id=user.id, company_id=company.id, role=role, is_active=True))
    return user


def _token(session, user: User) -> str:
    session_id = uuid4()
    now = datetime.now(timezone.utc)
    session.add(
        AuthSession(
            id=session_id,
            user_id=user.id,
            token_hash=f"hash-{session_id}",
            created_at=now,
            expires_at=now + timedelta(days=1),
        )
    )
    session.commit()
    token, _ = create_access_token(user.id, user.company_id, session_id)
    return token


def test_x_company_id_header_cannot_switch_tenant(db_session, client: TestClient) -> None:
    company_a = _company(db_session, slug="neg-header-a")
    company_b = _company(db_session, slug="neg-header-b")
    user_a = _user(db_session, company_a)
    db_session.commit()

    token_a = _token(db_session, user_a)
    response = client.get(
        "/api/v1/auth/me",
        headers={
            "Authorization": f"Bearer {token_a}",
            "X-Company-Id": str(company_b.id),
            "X-Avenqo-Tenant-Id": str(company_b.id),
        },
    )
    assert response.status_code == 200
    payload = response.json()
    company = payload.get("company") if isinstance(payload.get("company"), dict) else {}
    assert str(company.get("id") or payload.get("company_id") or "") == str(company_a.id)


def test_crm_client_idor_cross_tenant_returns_not_found(db_session, client: TestClient) -> None:
    company_a = _company(db_session, slug="neg-crm-a")
    company_b = _company(db_session, slug="neg-crm-b")
    user_a = _user(db_session, company_a)
    user_b = _user(db_session, company_b)
    foreign = CRMClient(
        company_id=company_a.id,
        first_name="Secret",
        last_name="Client",
        email="secret-a@example.com",
    )
    db_session.add(foreign)
    db_session.commit()

    token_b = _token(db_session, user_b)
    response = client.get(
        f"/api/v1/crm/clients/{foreign.id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert response.status_code == 404
    assert "secret-a@example.com" not in response.text


def test_staff_cannot_read_foreign_conversation(db_session, client: TestClient) -> None:
    company_a = _company(db_session, slug="neg-staff-a")
    company_b = _company(db_session, slug="neg-staff-b")
    owner_a = _user(db_session, company_a)
    staff_b = _user(db_session, company_b, role=UserRole.USER)
    db_session.commit()
    conversation = ConversationService(db_session).create(company_a.id, owner_a.id, "Private A")

    token_b = _token(db_session, staff_b)
    response = client.get(
        f"/api/v1/ai/chat/conversations/{conversation.id}",
        headers={"Authorization": f"Bearer {token_b}", "X-Company-Id": str(company_a.id)},
    )
    assert response.status_code == 404


def test_client_tenant_selectors_are_detected_and_stripped() -> None:
    assert client_tenant_override(headers={"X-Company-Id": "not-from-jwt"}) == "not-from-jwt"
    assert client_tenant_override(query={"tenant_id": "abc"}) == "abc"
    stripped = strip_client_tenant_arguments(
        {"company_id": "spoof", "content": "bonjour", "organization_id": "x"}
    )
    assert stripped == {"content": "bonjour"}
