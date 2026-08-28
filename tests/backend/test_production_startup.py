"""Démarrage production sans SMTP : l'app doit booter, email en erreur claire."""

from __future__ import annotations

import os

import pytest


@pytest.fixture()
def _clean_settings_cache():
    from backend.app.config.settings import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _build_settings(monkeypatch, **overrides):
    from backend.app.config.settings import Settings

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./var/avenqo-production.db")
    monkeypatch.setenv("AUTH_JWT_SECRET", "prod-jwt-secret-0123456789abcdef0123")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_dummy")
    monkeypatch.setenv("STRIPE_PRICE_DEMO", "price_demo_dummy")
    monkeypatch.setenv("STRIPE_PRICE_PROFESSIONAL", "price_pro_dummy")
    monkeypatch.setenv("STRIPE_PRICE_ENTERPRISE", "")
    monkeypatch.setenv("FRONTEND_URL", "https://app.avenqo.ca")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.avenqo.ca")
    monkeypatch.setenv("ALLOWED_HOSTS", "api.avenqo.ca")
    init_kwargs = {}
    for key, value in overrides.items():
        if value is None:
            # Chaîne vide = absent via blank_to_none (prioritaire sur .env local
            # qui contient de vraies clés Stripe de développement).
            monkeypatch.setenv(key, "")
        else:
            monkeypatch.setenv(key, value)
    return Settings()


def test_production_settings_boot_without_smtp_host(_clean_settings_cache, monkeypatch) -> None:
    settings = _build_settings(monkeypatch, SMTP_HOST=None)

    assert settings.environment == "production"
    assert settings.smtp_host is None


@pytest.mark.parametrize(
    "missing_key",
    [
        "DATABASE_URL",
        "AUTH_JWT_SECRET",
        "STRIPE_SECRET_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "STRIPE_PRICE_DEMO",
        "STRIPE_PRICE_PROFESSIONAL",
    ],
)
def test_production_settings_fail_fast_when_mandatory_config_is_missing(
    _clean_settings_cache,
    monkeypatch,
    missing_key: str,
) -> None:
    from backend.app.config.settings import Settings

    with pytest.raises(ValueError, match=missing_key):
        _build_settings(monkeypatch, **{missing_key: None})


def test_development_allows_missing_production_integrations(_clean_settings_cache, monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    for key in (
        "STRIPE_SECRET_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "STRIPE_PRICE_DEMO",
        "STRIPE_PRICE_PROFESSIONAL",
        "STRIPE_PRICE_ENTERPRISE",
    ):
        monkeypatch.setenv(key, "")

    from backend.app.config.settings import Settings

    settings = Settings()
    assert settings.billing_enabled is False


def test_billing_enabled_true_only_when_stripe_fully_configured(_clean_settings_cache, monkeypatch) -> None:
    settings = _build_settings(monkeypatch)
    assert settings.billing_enabled is True
    assert settings.stripe_price_enterprise is None
    assert settings.stripe_price_id("enterprise") is None

    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "")
    from backend.app.config.settings import Settings

    partial = Settings()
    assert partial.billing_enabled is False


def test_billing_provider_returns_clear_503_when_stripe_missing(_clean_settings_cache, monkeypatch) -> None:
    from fastapi import HTTPException
    import backend.app.dependencies.billing as billing_dep

    # Construire un settings Stripe-vide en neutralisant l'env ET le .env local
    # (pydantic-settings priorise le .env sur un kwargs None).
    for key in ("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET", "STRIPE_PRICE_DEMO", "STRIPE_PRICE_PROFESSIONAL", "STRIPE_PRICE_ENTERPRISE"):
        monkeypatch.setenv(key, "")
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("AUTH_JWT_SECRET", "prod-jwt-secret-0123456789abcdef0123")
    from backend.app.config.settings import Settings
    settings = Settings()
    assert settings.stripe_secret_key is None
    monkeypatch.setattr(billing_dep, "get_settings", lambda: settings)

    with pytest.raises(HTTPException) as exc_info:
        billing_dep.get_billing_provider()

    assert exc_info.value.status_code == 503
    assert "Stripe" in str(exc_info.value.detail)


def test_account_notifier_falls_back_to_logging_without_smtp(_clean_settings_cache, monkeypatch) -> None:
    settings = _build_settings(monkeypatch, SMTP_HOST=None)

    from backend.app.dependencies.auth import get_account_notifier
    from backend.app.services.account_notifications import LoggingAccountNotifier

    monkeypatch.setattr("backend.app.dependencies.auth.get_settings", lambda: settings)
    notifier = get_account_notifier()

    assert isinstance(notifier, LoggingAccountNotifier)


def test_smtp_notifier_raises_clear_error_when_host_missing(_clean_settings_cache, monkeypatch) -> None:
    settings = _build_settings(monkeypatch, SMTP_HOST=None)

    from backend.app.services.account_notifications import SMTPAccountNotifier

    with pytest.raises(ValueError, match="SMTP"):
        SMTPAccountNotifier(settings)
