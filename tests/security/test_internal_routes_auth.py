"""`/internal/*` must only accept the infrastructure scheduler token, never a user session."""

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
from backend.app.dependencies.training import get_training_dispatcher
from backend.app.models import AuthSession, Base, Company, CompanyMembership, User, UserRole
from backend.main import create_application
from tests.subscription_helpers import add_active_subscription

SCHEDULER_TOKEN = "scheduler-test-token-0123456789"

TENANT_SCOPED_ROUTES = [
    ("post", "/internal/retraining/check", {"module_code": "retail", "task_code": "bad_review"}),
    ("get", "/internal/versioning/versions?module_code=retail&task_code=bad_review", None),
    (
        "post",
        "/internal/versioning/compare",
        {"module_code": "retail", "task_code": "bad_review", "version_a": "v1", "version_b": "v2"},
    ),
    (
        "post",
        "/internal/versioning/rollback",
        {"module_code": "retail", "task_code": "bad_review", "target_version": "v1"},
    ),
]
GLOBAL_ROUTES = [
    ("post", "/internal/connector-ai/evaluate", None),
    ("post", "/internal/commerce/reconcile", None),
]


class _RecordingDispatcher:
    def __init__(self) -> None:
        self.tenants: list = []

    def dispatch_retraining_check(self, tenant, module_code, task_code, manual=False):
        self.tenants.append(tenant)
        return None


@pytest.fixture
def db_session(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'internal.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        yield session


@pytest.fixture
def dispatcher() -> _RecordingDispatcher:
    return _RecordingDispatcher()


def _client(db_session, dispatcher, monkeypatch, *, token: str) -> TestClient:
    monkeypatch.setenv("AUTH_JWT_SECRET", "a" * 32)
    monkeypatch.setenv("CONNECTOR_AI_SCHEDULER_TOKEN", token)
    get_settings.cache_clear()
    app = create_application()

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_training_dispatcher] = lambda: dispatcher
    return TestClient(app)


@pytest.fixture
def client(db_session, dispatcher, monkeypatch):
    with _client(db_session, dispatcher, monkeypatch, token=SCHEDULER_TOKEN) as test_client:
        yield test_client
    get_settings.cache_clear()


def _owner_with_token(session) -> tuple[Company, str]:
    company = Company(
        name="Co", slug=f"co-{uuid4().hex[:6]}", email=f"{uuid4().hex}@example.com", country="CA",
        timezone="America/Toronto", industry="Retail", subscription_plan="professional",
    )
    session.add(company)
    session.flush()
    add_active_subscription(session, company)
    user = User(
        company_id=company.id, first_name="Ow", last_name="Ner", email=f"{uuid4().hex}@example.com",
        password_hash="hash", role=UserRole.OWNER, email_verified_at=datetime.now(timezone.utc),
    )
    session.add(user)
    session.flush()
    session.add(CompanyMembership(user_id=user.id, company_id=company.id, role=UserRole.OWNER, is_active=True))
    session_id = uuid4()
    now = datetime.now(timezone.utc)
    session.add(AuthSession(
        id=session_id, user_id=user.id, token_hash=f"hash-{session_id}",
        created_at=now, expires_at=now + timedelta(days=1),
    ))
    session.commit()
    token, _ = create_access_token(user.id, company.id, session_id)
    return company, token


def _call(client: TestClient, method: str, path: str, body, headers: dict[str, str]):
    return client.request(method.upper(), path, json=body, headers=headers)


@pytest.mark.parametrize("method,path,body", TENANT_SCOPED_ROUTES + GLOBAL_ROUTES)
def test_owner_session_is_rejected_without_scheduler_token(client, db_session, method, path, body) -> None:
    company, token = _owner_with_token(db_session)
    response = _call(client, method, path, body, {
        "Authorization": f"Bearer {token}",
        "X-Avenqo-Tenant-Id": str(company.id),
    })
    assert response.status_code == 401


@pytest.mark.parametrize("method,path,body", TENANT_SCOPED_ROUTES + GLOBAL_ROUTES)
def test_wrong_scheduler_token_is_rejected(client, db_session, method, path, body) -> None:
    company, _ = _owner_with_token(db_session)
    response = _call(client, method, path, body, {
        "X-Avenqo-Scheduler-Token": "wrong",
        "X-Avenqo-Tenant-Id": str(company.id),
    })
    assert response.status_code == 401


@pytest.mark.parametrize("method,path,body", TENANT_SCOPED_ROUTES + GLOBAL_ROUTES)
def test_unconfigured_scheduler_disables_internal_routes(db_session, dispatcher, monkeypatch, method, path, body) -> None:
    company, _ = _owner_with_token(db_session)
    with _client(db_session, dispatcher, monkeypatch, token="") as client:
        response = _call(client, method, path, body, {
            "X-Avenqo-Scheduler-Token": "",
            "X-Avenqo-Tenant-Id": str(company.id),
        })
    get_settings.cache_clear()
    assert response.status_code == 503


@pytest.mark.parametrize("method,path,body", TENANT_SCOPED_ROUTES)
def test_unknown_or_missing_tenant_is_rejected(client, method, path, body) -> None:
    unknown = _call(client, method, path, body, {
        "X-Avenqo-Scheduler-Token": SCHEDULER_TOKEN,
        "X-Avenqo-Tenant-Id": str(uuid4()),
    })
    assert unknown.status_code == 404
    missing = _call(client, method, path, body, {"X-Avenqo-Scheduler-Token": SCHEDULER_TOKEN})
    assert missing.status_code == 422


def test_scheduler_acts_only_on_the_tenant_named_in_the_request(client, db_session, dispatcher) -> None:
    company_a, _ = _owner_with_token(db_session)
    _owner_with_token(db_session)
    response = client.post(
        "/internal/retraining/check",
        json={"module_code": "retail", "task_code": "bad_review"},
        headers={"X-Avenqo-Scheduler-Token": SCHEDULER_TOKEN, "X-Avenqo-Tenant-Id": str(company_a.id)},
    )
    assert response.status_code == 200
    assert response.json() == {"queued": False, "ai_job_id": None}
    assert [t.company_id for t in dispatcher.tenants] == [company_a.id]
    assert dispatcher.tenants[0].user_id is None
