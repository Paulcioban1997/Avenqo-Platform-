"""Tests ciblés de la configuration CORS par environnement (DEV vs PROD).

DEV  : localhost / 127.0.0.1 sur n'importe quel port autorisé via regex.
PROD : regex jamais utilisée — seules les origines explicites de CORS_ORIGINS.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _build_app(environment: str, cors_origins: list[str] | None = None):
    from backend.app.config.settings import get_settings
    from backend.main import create_application

    get_settings.cache_clear()
    import os

    old_env = os.environ.get("ENVIRONMENT")
    old_cors = os.environ.get("CORS_ORIGINS")
    prod_keys = (
        "DATABASE_URL",
        "AUTH_JWT_SECRET",
        "STRIPE_SECRET_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "STRIPE_PRICE_DEMO",
        "STRIPE_PRICE_PROFESSIONAL",
        "FRONTEND_URL",
        "ALLOWED_HOSTS",
    )
    old_prod = {k: os.environ.get(k) for k in prod_keys}
    os.environ["ENVIRONMENT"] = environment
    if cors_origins is not None:
        os.environ["CORS_ORIGINS"] = ",".join(cors_origins)
    if environment == "production":
        # Valeurs factices requises par la validation Settings en production.
        os.environ.setdefault("DATABASE_URL", "sqlite:///./var/cors-production-test.db")
        os.environ.setdefault("AUTH_JWT_SECRET", "test-only-prod-jwt-secret-0123456789abcdef")
        os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_dummy")
        os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_dummy")
        os.environ.setdefault("STRIPE_PRICE_DEMO", "price_demo_dummy")
        os.environ.setdefault("STRIPE_PRICE_PROFESSIONAL", "price_pro_dummy")
        os.environ.setdefault("FRONTEND_URL", "https://app.avenqo.ca")
        os.environ.setdefault("ALLOWED_HOSTS", "testserver")
    try:
        app = create_application()
    finally:
        if old_env is None:
            os.environ.pop("ENVIRONMENT", None)
        else:
            os.environ["ENVIRONMENT"] = old_env
        if old_cors is None:
            os.environ.pop("CORS_ORIGINS", None)
        else:
            os.environ["CORS_ORIGINS"] = old_cors
        for k, v in old_prod.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        get_settings.cache_clear()
    return app


def _preflight(client: TestClient, origin: str) -> tuple[int, str | None]:
    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )
    return response.status_code, response.headers.get("access-control-allow-origin")


def test_dev_allows_localhost_on_random_port() -> None:
    app = _build_app("development")
    status, allow_origin = _preflight(TestClient(app), "http://localhost:58404")

    assert status == 200
    assert allow_origin == "http://localhost:58404"


def test_dev_allows_localhost_8080() -> None:
    app = _build_app("development")
    status, allow_origin = _preflight(TestClient(app), "http://localhost:8080")

    assert status == 200
    assert allow_origin == "http://localhost:8080"


def test_prod_rejects_localhost_random_port() -> None:
    app = _build_app(
        "production",
        cors_origins=["https://app.avenqo.ca", "https://avenqo.ca"],
    )
    status, allow_origin = _preflight(TestClient(app), "http://localhost:58404")

    assert status == 400
    assert allow_origin is None


def test_prod_allows_explicit_production_origin() -> None:
    app = _build_app(
        "production",
        cors_origins=["https://app.avenqo.ca", "https://avenqo.ca"],
    )
    status, allow_origin = _preflight(TestClient(app), "https://app.avenqo.ca")

    assert status == 200
    assert allow_origin == "https://app.avenqo.ca"
