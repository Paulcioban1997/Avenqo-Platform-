"""Tests de validation de l'authentification unifiée par cookies HttpOnly et CSRF."""

from collections.abc import Generator
from datetime import datetime, timezone
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.database import get_db
from backend.app.dependencies.auth import get_account_notifier
from backend.app.models import Base, Company, User
from backend.app.models.base import CompanyStatus, UserRole
from backend.app.core.security import hash_password
from backend.main import create_application


class RecordingNotifier:
    email_delivery_configured = True

    def __init__(self) -> None:
        self.verification_tokens: dict[str, str] = {}
        self.reset_tokens: dict[str, str] = {}

    def send_email_verification(self, email: str, token: str) -> None:
        self.verification_tokens[email] = token

    def send_password_reset(self, email: str, token: str) -> None:
        self.reset_tokens[email] = token


@pytest.fixture
def auth_env(tmp_path: Path) -> Generator[tuple[TestClient, sessionmaker[Session], User, User], None, None]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'auth_cookie.db'}",
        connect_args={"check_same_thread": False},
    )
    testing_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    notifier = RecordingNotifier()
    app = create_application()

    def override_db() -> Generator[Session, None, None]:
        session = testing_session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_account_notifier] = lambda: notifier

    with testing_session() as session:
        company = Company(
            name="Test Auth Company",
            slug="test-auth-company",
            email="billing@testauth.ca",
            country="Canada",
            timezone="America/Toronto",
            industry="E-commerce",
            preferred_language="fr-CA",
            subscription_plan="pro",
            status=CompanyStatus.ACTIVE,
        )
        session.add(company)
        session.flush()

        standard_user = User(
            company_id=company.id,
            email="standard@testauth.ca",
            password_hash=hash_password("AvenqoTest123!"),
            first_name="Jean",
            last_name="Standard",
            role=UserRole.USER,
            is_active=True,
            email_verified_at=datetime.now(timezone.utc),
            is_platform_admin=False,
        )
        admin_user = User(
            company_id=company.id,
            email="admin@testauth.ca",
            password_hash=hash_password("AvenqoAdmin123!"),
            first_name="Alice",
            last_name="Admin",
            role=UserRole.OWNER,
            is_active=True,
            email_verified_at=datetime.now(timezone.utc),
            is_platform_admin=True,
        )
        session.add_all([standard_user, admin_user])
        session.commit()

    with TestClient(app) as client:
        yield client, testing_session, standard_user, admin_user


def test_login_sets_httponly_cookies(auth_env):
    """Vérifie que /login positionne les cookies avenqo_access_token et avenqo_refresh_token."""
    client, _, standard_user, _ = auth_env

    response = client.post(
        "/api/v1/auth/login",
        json={"email": standard_user.email, "password": "AvenqoTest123!"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data

    # Vérification des cookies
    cookies = response.cookies
    assert "avenqo_access_token" in cookies
    assert "avenqo_refresh_token" in cookies
    assert "avenqo_csrf" in cookies

    # Headers Set-Cookie
    set_cookie_headers = response.headers.get_list("set-cookie")
    access_cookie_header = next((h for h in set_cookie_headers if "avenqo_access_token=" in h), "")
    refresh_cookie_header = next((h for h in set_cookie_headers if "avenqo_refresh_token=" in h), "")

    assert "httponly" in access_cookie_header.lower()
    assert "samesite=lax" in access_cookie_header.lower()
    assert "httponly" in refresh_cookie_header.lower()
    assert "samesite=strict" in refresh_cookie_header.lower()


def test_auth_me_via_cookie_without_bearer(auth_env):
    """Vérifie que /auth/me s'authentifie directement par cookie sans header Authorization."""
    client, _, standard_user, _ = auth_env

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": standard_user.email, "password": "AvenqoTest123!"},
    )
    assert login_resp.status_code == 200

    # Note: client persistant conserve automatiquement les cookies
    # Appel /auth/me sans header Authorization
    me_resp = client.get("/api/v1/auth/me")
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["user"]["email"] == standard_user.email


def test_cookie_refresh_and_rotation(auth_env):
    """Vérifie le rafraîchissement automatique de session par cookie et sa rotation."""
    client, _, standard_user, _ = auth_env

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": standard_user.email, "password": "AvenqoTest123!"},
    )
    first_refresh_token = login_resp.cookies.get("avenqo_refresh_token")

    # Refresh sans JSON body (utilise le cookie)
    refresh_resp = client.post("/api/v1/auth/refresh")
    assert refresh_resp.status_code == 200

    new_refresh_token = refresh_resp.cookies.get("avenqo_refresh_token")
    assert new_refresh_token is not None
    assert new_refresh_token != first_refresh_token


def test_logout_clears_cookies_and_revokes_session(auth_env):
    """Vérifie que /logout révoque la session et supprime les cookies."""
    client, _, standard_user, _ = auth_env

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": standard_user.email, "password": "AvenqoTest123!"},
    )
    assert login_resp.status_code == 200

    logout_resp = client.post("/api/v1/auth/logout", headers={"Sec-Fetch-Site": "same-origin"})
    assert logout_resp.status_code == 200

    # Session révoquée -> /auth/me renvoie 401
    after_logout_resp = client.get("/api/v1/auth/me")
    assert after_logout_resp.status_code == 401


def test_csrf_protection_on_mutable_requests(auth_env):
    """Vérifie la protection CSRF sur les requêtes mutables sous authentification par cookie."""
    client, _, standard_user, _ = auth_env

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": standard_user.email, "password": "AvenqoTest123!"},
    )
    assert login_resp.status_code == 200
    csrf_token = login_resp.cookies.get("avenqo_csrf")

    # Requête cross-site sans header CSRF -> Refusée (403)
    denied_resp = client.post("/api/v1/auth/logout", headers={"Sec-Fetch-Site": "cross-site"})
    assert denied_resp.status_code == 403

    # Requête cross-site avec double-submit matching header -> Acceptée (200)
    allowed_with_header = client.post(
        "/api/v1/auth/logout",
        headers={"Sec-Fetch-Site": "cross-site", "X-CSRF-Token": csrf_token},
    )
    assert allowed_with_header.status_code == 200


def test_admin_permissions_with_cookie_auth(auth_env):
    """Vérifie que l'accès admin est strictement réservé même sous authentification cookie."""
    client, _, standard_user, admin_user = auth_env

    # 1. Connexion standard user
    client.post(
        "/api/v1/auth/login",
        json={"email": standard_user.email, "password": "AvenqoTest123!"},
    )

    # Accès route admin -> Refusé (403)
    std_admin_resp = client.get("/api/v1/admin/companies")
    assert std_admin_resp.status_code == 403

    # 2. Connexion platform admin
    client.post(
        "/api/v1/auth/login",
        json={"email": admin_user.email, "password": "AvenqoAdmin123!"},
    )

    # Accès route admin -> Accepté (200)
    adm_admin_resp = client.get("/api/v1/admin/companies")
    assert adm_admin_resp.status_code == 200
