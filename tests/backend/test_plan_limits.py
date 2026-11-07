from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.config.settings import get_settings
from backend.app.core.security import create_access_token
from backend.app.database import get_db
from backend.app.dependencies.auth import get_account_notifier
from backend.app.models import AuthSession, Base, Company, CompanyMembership, User, UserRole
from backend.app.models.enterprise_override import EnterpriseOverride
from backend.app.services.plan_limits_service import PlanLimitReached, PlanLimitsService
from backend.main import create_application
from tests.subscription_helpers import add_active_subscription


class _NullNotifier:
    def send_email_verification(self, email: str, token: str) -> None:
        pass

    def send_password_reset(self, email: str, token: str) -> None:
        pass


@pytest.fixture
def db_session(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'limits.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        yield session


@pytest.fixture
def client(db_session, monkeypatch):
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


def _company(session, plan: str) -> Company:
    company = Company(
        name=f"Co {plan}", slug=f"{plan}-{uuid4().hex[:6]}", email=f"{uuid4().hex}@example.com",
        country="CA", timezone="America/Toronto", industry="Retail", subscription_plan=plan,
    )
    session.add(company)
    session.flush()
    add_active_subscription(session, company)
    session.flush()
    return company


def _user(session, company: Company, role: UserRole = UserRole.USER, *, active: bool = True, platform: bool = False) -> User:
    user = User(
        company_id=company.id, first_name="T", last_name="U", email=f"{uuid4().hex}@example.com",
        password_hash="hash", role=role, is_active=active, is_platform_admin=platform,
        email_verified_at=datetime.now(timezone.utc),
    )
    session.add(user)
    session.flush()
    return user


def _token(session, user: User) -> str:
    session_id = uuid4()
    now = datetime.now(timezone.utc)
    session.add(AuthSession(
        id=session_id, user_id=user.id, token_hash=f"hash-{session_id}",
        created_at=now, expires_at=now + timedelta(days=1),
    ))
    session.commit()
    token, _ = create_access_token(user.id, user.company_id, session_id)
    return token


@pytest.mark.parametrize(
    "plan,users,sites,agents,calls",
    [("base", 3, 1, 1, 1), ("demo", 3, 1, 1, 1), ("professional", 10, 3, 3, 2), ("enterprise", None, None, None, None)],
)
def test_catalogue_limits_per_plan(db_session, plan, users, sites, agents, calls) -> None:
    company = _company(db_session, plan)
    limits = PlanLimitsService(db_session).limits_for(company.id)
    assert (limits.max_users, limits.max_sites, limits.max_voice_agents, limits.max_concurrent_calls) == (
        users, sites, agents, calls,
    )


def test_every_plan_code_has_an_explicit_rank() -> None:
    from backend.app.ai.tools.plans import _PLAN_RANK, plan_meets_minimum
    from payments.plans import PlanCode

    assert {code.value for code in PlanCode} == set(_PLAN_RANK)
    assert plan_meets_minimum("base", "base") and not plan_meets_minimum("base", "professional")
    assert plan_meets_minimum("professional", "base") and not plan_meets_minimum("professional", "enterprise")
    assert plan_meets_minimum("enterprise", "professional")


def test_enterprise_contract_overrides_apply_and_invalid_values_are_ignored(db_session) -> None:
    company = _company(db_session, "enterprise")
    db_session.add(EnterpriseOverride(
        company_id=company.id,
        quota_overrides={"max_users": 40, "max_sites": -1, "max_voice_agents": True, "max_concurrent_calls": 6},
    ))
    db_session.flush()
    limits = PlanLimitsService(db_session).limits_for(company.id)
    assert limits.max_users == 40
    assert limits.max_sites is None
    assert limits.max_voice_agents is None
    assert limits.max_concurrent_calls == 6


def test_seat_count_ignores_inactive_and_platform_admins_and_includes_members(db_session) -> None:
    company, other = _company(db_session, "base"), _company(db_session, "base")
    _user(db_session, company, UserRole.OWNER)
    _user(db_session, company, active=False)
    _user(db_session, company, platform=True)
    member = _user(db_session, other)
    db_session.add(CompanyMembership(user_id=member.id, company_id=company.id, role=UserRole.USER, is_active=True))
    db_session.flush()
    assert len(PlanLimitsService(db_session).active_user_ids(company.id)) == 2
    assert len(PlanLimitsService(db_session).active_user_ids(other.id)) == 1


def test_ensure_capacity_raises_at_limit(db_session) -> None:
    company = _company(db_session, "professional")
    service = PlanLimitsService(db_session)
    service.ensure_capacity(company.id, "max_voice_agents", current=2)
    with pytest.raises(PlanLimitReached) as error:
        service.ensure_capacity(company.id, "max_voice_agents", current=3)
    assert (error.value.limit_key, error.value.limit, error.value.plan_code) == ("max_voice_agents", 3, "professional")


def _create(client, token, role="user"):
    return client.post(
        "/api/v1/employees",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "first_name": "New", "last_name": "Hire", "email": f"{uuid4().hex}@example.com",
            "password": "Correct-Horse-Battery-9", "role": role,
        },
    )


def test_base_plan_blocks_fourth_active_user_over_api(client, db_session) -> None:
    company = _company(db_session, "base")
    owner = _user(db_session, company, UserRole.OWNER)
    token = _token(db_session, owner)

    assert _create(client, token).status_code == 201
    assert _create(client, token).status_code == 201
    blocked = _create(client, token)
    assert blocked.status_code == 409
    error = blocked.json()["error"]
    assert error["code"] == "plan_limit_reached"
    assert error["details"] == {"limit_key": "max_users", "limit": 3, "plan_code": "base"}
    assert db_session.query(User).filter(User.company_id == company.id).count() == 3


def test_reactivation_counts_against_the_limit(client, db_session) -> None:
    company = _company(db_session, "base")
    owner = _user(db_session, company, UserRole.OWNER)
    _user(db_session, company)
    _user(db_session, company)
    dormant = _user(db_session, company, active=False)
    token = _token(db_session, owner)

    response = client.patch(
        f"/api/v1/employees/{dormant.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"is_active": True},
    )
    assert response.status_code == 409
    db_session.refresh(dormant)
    assert dormant.is_active is False


def test_limit_is_per_tenant(client, db_session) -> None:
    full = _company(db_session, "base")
    _user(db_session, full, UserRole.OWNER)
    _user(db_session, full)
    _user(db_session, full)
    roomy = _company(db_session, "base")
    owner = _user(db_session, roomy, UserRole.OWNER)
    assert _create(client, _token(db_session, owner)).status_code == 201


def test_professional_allows_ten_users(client, db_session) -> None:
    company = _company(db_session, "professional")
    owner = _user(db_session, company, UserRole.OWNER)
    token = _token(db_session, owner)
    statuses = [_create(client, token).status_code for _ in range(10)]
    assert statuses == [201] * 9 + [409]
