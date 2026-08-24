"""Phase 34 — Security regression suite (tests/security/).

Regroupe les protections critiques transverses en un seul endroit :
IDOR (accès direct par identifiant cross-tenant), autorisation admin,
non-fuite de secrets. Ne duplique pas les tests d'isolation déjà présents
dans tests/backend/test_phase21/24/25/26/27/30_1/31/33 — se concentre sur
les endpoints qui n'avaient pas encore de test IDOR explicite.
"""

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
from backend.app.database import get_db
from backend.app.dependencies.auth import get_account_notifier
from backend.app.models import AuthSession, Base, Company, User, UserRole
from backend.main import create_application


class _NullNotifier:
    def send_email_verification(self, email: str, token: str) -> None:
        pass

    def send_password_reset(self, email: str, token: str) -> None:
        pass


@pytest.fixture
def db_session(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'security.db'}")
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
        name=f"Co {slug}", slug=slug, email=f"{slug}@example.com", country="CA",
        timezone="America/Toronto", industry="Retail", subscription_plan="professional",
    )
    session.add(company)
    session.flush()
    return company


def _user(session, company: Company, *, role: UserRole = UserRole.OWNER) -> User:
    user = User(
        company_id=company.id, first_name="Ana", last_name="Lyst",
        email=f"user-{uuid4()}@example.com", password_hash="hash", role=role,
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


def test_conversation_idor_cross_tenant_returns_not_found(db_session, client: TestClient) -> None:
    company_a = _company(db_session, slug="idor-a")
    company_b = _company(db_session, slug="idor-b")
    user_a = _user(db_session, company_a)
    user_b = _user(db_session, company_b)
    db_session.commit()

    conversation = ConversationService(db_session).create(company_a.id, user_a.id, "Private A")

    token_b = _token(db_session, user_b)
    response = client.get(
        f"/api/v1/ai/chat/conversations/{conversation.id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert response.status_code == 404


def test_conversation_message_idor_cross_tenant_returns_not_found(db_session, client: TestClient) -> None:
    company_a = _company(db_session, slug="idor-msg-a")
    company_b = _company(db_session, slug="idor-msg-b")
    user_a = _user(db_session, company_a)
    user_b = _user(db_session, company_b)
    db_session.commit()

    conversation = ConversationService(db_session).create(company_a.id, user_a.id, "Private A")

    token_b = _token(db_session, user_b)
    response = client.post(
        f"/api/v1/ai/chat/conversations/{conversation.id}/messages",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"content": "gimme the data"},
    )
    assert response.status_code == 404


def test_tenant_owner_cannot_reach_admin_company_detail_for_any_company(db_session, client: TestClient) -> None:
    company_a = _company(db_session, slug="idor-admin-a")
    owner_a = _user(db_session, company_a, role=UserRole.OWNER)
    company_b = _company(db_session, slug="idor-admin-b")
    db_session.commit()

    token_a = _token(db_session, owner_a)
    response = client.get(
        f"/api/v1/admin/companies/{company_b.id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert response.status_code in (401, 403)


def test_anonymous_cannot_access_any_sensitive_route(client: TestClient) -> None:
    for path in (
        "/api/v1/admin/dashboard",
        "/api/v1/billing/subscription",
        "/api/v1/employees",
        "/api/v1/ai/chat/conversations",
    ):
        response = client.get(path)
        assert response.status_code in (401, 403), path


def test_path_traversal_in_company_id_is_rejected_not_500(client: TestClient) -> None:
    response = client.get("/api/v1/admin/companies/../../etc/passwd")
    assert response.status_code in (401, 403, 404, 422)


# ---------------------------------------------------------------------------
# Backup/restore : opérations internes uniquement (remédiation post-Phase 34)
# ---------------------------------------------------------------------------


def test_no_http_route_exposes_backup_or_restore(client: TestClient) -> None:
    """Backup/restore sont des outils CLI internes (scripts/backup_db.py,
    scripts/restore_db.py) — aucune route HTTP ne doit jamais les exposer,
    qu'un tenant ne pourrait alors jamais déclencher via l'API publique."""

    schema = client.get("/openapi.json").json()
    paths = " ".join(schema["paths"].keys()).lower()
    assert "backup" not in paths
    assert "restore" not in paths

    for guessed_path in (
        "/api/v1/admin/backups",
        "/api/v1/admin/backup",
        "/api/v1/admin/restore",
        "/api/v1/backups",
        "/api/v1/backup/create",
        "/api/v1/backup/restore",
    ):
        response = client.get(guessed_path)
        assert response.status_code == 404, guessed_path
        response = client.post(guessed_path)
        assert response.status_code == 404, guessed_path


def test_backup_service_path_traversal_is_rejected(tmp_path) -> None:
    from backend.app.config.settings import Settings
    from backend.app.services.backup_service import BackupError, BackupService

    settings = Settings(
        AUTH_JWT_SECRET="f" * 32,
        DATABASE_URL=f"sqlite:///{tmp_path / 'unused.db'}",
        BACKUP_ROOT=str(tmp_path / "backups"),
    )
    service = BackupService(settings)
    for malicious_id in ("../../etc/passwd", "/etc/passwd", ".."):
        with pytest.raises(BackupError):
            service.verify_backup(malicious_id)
