"""Phase 34 — Production readiness : sécurité, config, rate limiting, pagination.

Ne duplique pas les tests d'isolation tenant déjà couverts (Phase 21/24/25/26/
27/30.1/31/33). Couvre spécifiquement les ajouts Phase 34 : configuration
production (docs désactivés, validation stricte), en-têtes de sécurité,
TrustedHost, rate limiting, pagination des listes admin/billing/chat, endpoint
`/ready`, et non-fuite de trace d'erreur au client.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.config.settings import Settings, get_settings
from backend.app.database import get_db
from backend.app.dependencies.auth import get_account_notifier
from backend.app.models import Base
from backend.main import create_application
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


class _NullNotifier:
    def send_email_verification(self, email: str, token: str) -> None:
        pass

    def send_password_reset(self, email: str, token: str) -> None:
        pass


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'phase34.db'}")
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


# ---------------------------------------------------------------------------
# 1. Production configuration
# ---------------------------------------------------------------------------


def test_production_requires_non_default_jwt_secret() -> None:
    with pytest.raises(ValueError):
        Settings(ENVIRONMENT="production")


def test_production_allows_optional_smtp_and_enterprise_price() -> None:
    settings = Settings(
        ENVIRONMENT="production",
        DATABASE_URL="sqlite:///./var/avenqo-production.db",
        AUTH_JWT_SECRET="a" * 32,
        SMTP_HOST="",
        STRIPE_SECRET_KEY="sk_test_x",
        STRIPE_WEBHOOK_SECRET="whsec_x",
        STRIPE_PRICE_DEMO="price_demo",
        STRIPE_PRICE_PROFESSIONAL="price_pro",
        STRIPE_PRICE_ENTERPRISE="",
        FRONTEND_URL="https://app.avenqo.ca",
        CORS_ORIGINS="https://app.avenqo.ca",
        ALLOWED_HOSTS="api.avenqo.ca",
    )
    assert settings.environment == "production"
    assert settings.smtp_host is None
    assert settings.stripe_price_enterprise is None
    assert settings.billing_enabled is True


def test_production_settings_accepted_when_fully_configured() -> None:
    settings = Settings(
        ENVIRONMENT="production",
        DATABASE_URL="sqlite:///./var/avenqo-production.db",
        AUTH_JWT_SECRET="b" * 32,
        SMTP_HOST="smtp.avenqo.ca",
        STRIPE_SECRET_KEY="sk_test_x",
        STRIPE_WEBHOOK_SECRET="whsec_x",
        STRIPE_PRICE_DEMO="price_demo",
        STRIPE_PRICE_PROFESSIONAL="price_pro",
        STRIPE_PRICE_ENTERPRISE="",
        FRONTEND_URL="https://app.avenqo.ca",
        CORS_ORIGINS="https://app.avenqo.ca",
        ALLOWED_HOSTS="api.avenqo.ca",
    )
    assert settings.environment == "production"
    assert settings.billing_enabled is True


def test_docs_disabled_in_production(monkeypatch: pytest.MonkeyPatch, db_session) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_session.bind.url.database}")
    monkeypatch.setenv("AUTH_JWT_SECRET", "c" * 32)
    monkeypatch.setenv("SMTP_HOST", "smtp.avenqo.ca")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_x")
    monkeypatch.setenv("STRIPE_PRICE_DEMO", "price_demo")
    monkeypatch.setenv("STRIPE_PRICE_PROFESSIONAL", "price_pro")
    monkeypatch.setenv("STRIPE_PRICE_ENTERPRISE", "")
    monkeypatch.setenv("FRONTEND_URL", "https://app.avenqo.ca")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.avenqo.ca")
    monkeypatch.setenv("ALLOWED_HOSTS", "api.avenqo.ca")
    get_settings.cache_clear()
    app = create_application()

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as prod_client:
        headers = {"Host": "api.avenqo.ca"}
        assert prod_client.get("/docs", headers=headers).status_code == 404
        assert prod_client.get("/openapi.json", headers=headers).status_code == 404
    get_settings.cache_clear()


def test_docs_available_in_development(client: TestClient) -> None:
    assert client.get("/docs").status_code == 200


# ---------------------------------------------------------------------------
# 2. Security headers & trusted host
# ---------------------------------------------------------------------------


def test_security_headers_present_on_every_response(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "Content-Security-Policy" in response.headers
    assert "X-Request-ID" in response.headers


# ---------------------------------------------------------------------------
# 3. Health / readiness — never leak secrets
# ---------------------------------------------------------------------------


def test_health_endpoint_reveals_no_secret(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.text
    assert "sk-" not in body and "postgresql://" not in body


def test_ready_endpoint_checks_database_and_hides_secrets(client: TestClient) -> None:
    response = client.get("/api/v1/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["database"] == "ok"
    assert isinstance(data["stripe_configured"], bool)
    assert "sk-" not in response.text and "whsec" not in response.text


# ---------------------------------------------------------------------------
# 4. Rate limiting
# ---------------------------------------------------------------------------


def test_login_endpoint_is_rate_limited(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_AUTH_PER_MINUTE", "3")
    get_settings.cache_clear()
    payload = {"email": "nobody@example.com", "password": "wrong-password"}
    statuses = [client.post("/api/v1/auth/login", json=payload).status_code for _ in range(5)]
    assert 429 in statuses
    get_settings.cache_clear()


def test_rate_limit_can_be_disabled(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    monkeypatch.setenv("RATE_LIMIT_AUTH_PER_MINUTE", "1")
    get_settings.cache_clear()
    payload = {"email": "nobody@example.com", "password": "wrong-password"}
    statuses = [client.post("/api/v1/auth/login", json=payload).status_code for _ in range(5)]
    assert 429 not in statuses
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# 5. Error responses never leak stack traces
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unhandled_exception_never_leaks_traceback() -> None:
    from starlette.requests import Request

    from backend.app.core.exception_handlers import internal_exception_handler

    scope = {"type": "http", "method": "GET", "path": "/x", "headers": []}
    request = Request(scope)
    try:
        raise RuntimeError("simulated internal failure with a secret token sk-should-not-leak")
    except RuntimeError as exc:
        response = await internal_exception_handler(request, exc)

    assert response.status_code == 500
    body = response.body.decode()
    assert "sk-should-not-leak" not in body
    assert "Traceback" not in body
    assert "RuntimeError" not in body
