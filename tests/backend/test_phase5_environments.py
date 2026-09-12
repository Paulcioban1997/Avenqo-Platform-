"""Tests for Phase 5: FastAPI Environments Configuration (Local / Staging / Production)."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.config.settings import Settings
from backend.main import create_application


def test_local_environment_defaults():
    """Verify local development configuration has safe defaults and Secure=False cookies."""
    settings = Settings(
        ENVIRONMENT="development",
        DATABASE_URL="sqlite:///./var/avenqo.db",
        AUTH_JWT_SECRET="development-only-change-this-jwt-secret",
    )
    assert settings.environment == "development"
    assert settings.is_secure_cookie is False
    assert settings.frontend_url == "http://localhost:3000"
    assert "http://localhost:3000" in settings.cors_origins


def test_postgres_url_normalization():
    """Verify legacy postgres:// URLs from Railway/Heroku are automatically converted to postgresql://."""
    settings = Settings(
        ENVIRONMENT="development",
        DATABASE_URL="postgres://user:pass@ep-sandbox.railway.internal:5432/railway",
    )
    assert settings.database_url.startswith("postgresql://")
    assert not settings.database_url.startswith("postgres://")


def test_staging_environment_requires_secure_cookies_and_strong_secret():
    """Verify staging / sandbox environment enforces Secure=True cookies and rejects default secrets."""
    settings = Settings(
        ENVIRONMENT="staging",
        DATABASE_URL="postgresql://user:pass@ep-sandbox.railway.internal:5432/railway",
        AUTH_JWT_SECRET="super-strong-staging-secret-key-with-over-32-characters!",
    )
    assert settings.is_secure_cookie is True

    # Rejects default secret in staging
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            ENVIRONMENT="staging",
            AUTH_JWT_SECRET="development-only-change-this-jwt-secret",
        )
    assert "AUTH_JWT_SECRET" in str(exc_info.value)


def test_production_rejects_default_jwt_secret():
    """Production must refuse startup if AUTH_JWT_SECRET uses default placeholder."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            ENVIRONMENT="production",
            DATABASE_URL="postgresql://user:pass@ep-prod.railway.internal:5432/railway",
            AUTH_JWT_SECRET="development-only-change-this-jwt-secret",
            STRIPE_SECRET_KEY="sk_live_123",
            STRIPE_WEBHOOK_SECRET="whsec_123",
            STRIPE_PRICE_DEMO="price_demo_123",
            STRIPE_PRICE_PROFESSIONAL="price_pro_123",
            FRONTEND_URL="https://avenqo.ca",
            CORS_ORIGINS=["https://avenqo.ca"],
            ALLOWED_HOSTS=["api.avenqo.ca", "backend.railway.internal"],
        )
    assert "AUTH_JWT_SECRET" in str(exc_info.value)

    # Rejects second known placeholder
    with pytest.raises(ValidationError) as exc_info2:
        Settings(
            ENVIRONMENT="production",
            DATABASE_URL="postgresql://user:pass@ep-prod.railway.internal:5432/railway",
            AUTH_JWT_SECRET="replace-with-at-least-32-random-characters",
            STRIPE_SECRET_KEY="sk_live_123",
            STRIPE_WEBHOOK_SECRET="whsec_123",
            STRIPE_PRICE_DEMO="price_demo_123",
            STRIPE_PRICE_PROFESSIONAL="price_pro_123",
            FRONTEND_URL="https://avenqo.ca",
            CORS_ORIGINS=["https://avenqo.ca"],
            ALLOWED_HOSTS=["api.avenqo.ca"],
        )
    assert "AUTH_JWT_SECRET" in str(exc_info2.value)


def test_production_rejects_empty_critical_secrets():
    """Production must refuse startup if critical secrets or Stripe keys are missing."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            ENVIRONMENT="production",
            DATABASE_URL="postgresql://user:pass@ep-prod.railway.internal:5432/railway",
            AUTH_JWT_SECRET="super-strong-production-secret-key-32-characters-minimum!",
            STRIPE_SECRET_KEY="",
            STRIPE_WEBHOOK_SECRET="",
            STRIPE_PRICE_DEMO="",
            STRIPE_PRICE_PROFESSIONAL="",
            FRONTEND_URL="https://avenqo.ca",
            CORS_ORIGINS=["https://avenqo.ca"],
            ALLOWED_HOSTS=["api.avenqo.ca"],
        )
    err = str(exc_info.value)
    assert "STRIPE_SECRET_KEY" in err
    assert "STRIPE_WEBHOOK_SECRET" in err
    assert "STRIPE_PRICE_DEMO" in err
    assert "STRIPE_PRICE_PROFESSIONAL" in err


def test_production_rejects_wildcard_cors_and_insecure_origins():
    """Production must refuse wildcard '*' or insecure http:// in CORS_ORIGINS."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            ENVIRONMENT="production",
            DATABASE_URL="postgresql://user:pass@ep-prod.railway.internal:5432/railway",
            AUTH_JWT_SECRET="super-strong-production-secret-key-32-characters-minimum!",
            STRIPE_SECRET_KEY="sk_live_123",
            STRIPE_WEBHOOK_SECRET="whsec_123",
            STRIPE_PRICE_DEMO="price_demo_123",
            STRIPE_PRICE_PROFESSIONAL="price_pro_123",
            FRONTEND_URL="https://avenqo.ca",
            CORS_ORIGINS=["*"],
            ALLOWED_HOSTS=["api.avenqo.ca"],
        )
    assert "CORS_ORIGINS" in str(exc_info.value)

    # Insecure http:// origin
    with pytest.raises(ValidationError) as exc_info2:
        Settings(
            ENVIRONMENT="production",
            DATABASE_URL="postgresql://user:pass@ep-prod.railway.internal:5432/railway",
            AUTH_JWT_SECRET="super-strong-production-secret-key-32-characters-minimum!",
            STRIPE_SECRET_KEY="sk_live_123",
            STRIPE_WEBHOOK_SECRET="whsec_123",
            STRIPE_PRICE_DEMO="price_demo_123",
            STRIPE_PRICE_PROFESSIONAL="price_pro_123",
            FRONTEND_URL="https://avenqo.ca",
            CORS_ORIGINS=["http://insecure.avenqo.ca"],
            ALLOWED_HOSTS=["api.avenqo.ca"],
        )
    assert "CORS_ORIGINS" in str(exc_info2.value)


def test_production_accepts_valid_canonical_configuration():
    """Production must successfully validate when all production parameters are compliant."""
    settings = Settings(
        ENVIRONMENT="production",
        DATABASE_URL="postgresql://user:pass@ep-prod.railway.internal:5432/railway",
        AUTH_JWT_SECRET="super-strong-production-secret-key-32-characters-minimum!",
        STRIPE_SECRET_KEY="sk_live_test_12345",
        STRIPE_WEBHOOK_SECRET="whsec_test_12345",
        STRIPE_PRICE_DEMO="price_demo_12345",
        STRIPE_PRICE_PROFESSIONAL="price_pro_12345",
        FRONTEND_URL="https://avenqo.ca",
        CORS_ORIGINS=["https://avenqo.ca", "https://www.avenqo.ca"],
        ALLOWED_HOSTS=["api.avenqo.ca", "avenqo.ca", "backend.railway.internal"],
    )
    assert settings.environment == "production"
    assert settings.is_secure_cookie is True
    assert settings.frontend_url == "https://avenqo.ca"


def test_health_and_readiness_endpoints():
    """Verify /health and /ready at both root and /api/v1/ without exposing sensitive data."""
    app = create_application()
    client = TestClient(app)

    # Root /health
    r_health_root = client.get("/health")
    assert r_health_root.status_code == 200
    data_health = r_health_root.json()
    assert data_health["status"] == "healthy"
    assert "application" in data_health
    assert "version" in data_health
    assert "environment" in data_health

    # Prefix /api/v1/health
    r_health_v1 = client.get("/api/v1/health")
    assert r_health_v1.status_code == 200
    assert r_health_v1.json() == data_health

    # Root /ready
    r_ready_root = client.get("/ready")
    assert r_ready_root.status_code == 200
    data_ready = r_ready_root.json()
    assert data_ready["status"] in ("ready", "degraded")
    assert data_ready["database"] == "ok"
    assert data_ready["migrations"] in ("ok", "unverified", "pending")
    assert "artifact_storage" in data_ready
    assert "stripe_configured" in data_ready

    # Ensure no secrets leaked in ready response
    content_str = r_ready_root.text
    for sensitive in ("password", "secret", "jwt", "key", "token"):
        assert f'"{sensitive}": "' not in content_str

    # Prefix /api/v1/ready
    r_ready_v1 = client.get("/api/v1/ready")
    assert r_ready_v1.status_code == 200
    assert r_ready_v1.json() == data_ready
