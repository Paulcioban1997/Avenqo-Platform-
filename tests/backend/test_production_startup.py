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
    monkeypatch.setenv("AUTH_JWT_SECRET", "prod-jwt-secret-0123456789abcdef0123")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_dummy")
    monkeypatch.setenv("STRIPE_PRICE_DEMO", "price_demo_dummy")
    monkeypatch.setenv("STRIPE_PRICE_PROFESSIONAL", "price_pro_dummy")
    monkeypatch.setenv("STRIPE_PRICE_ENTERPRISE", "price_ent_dummy")
    init_kwargs = {}
    for key, value in overrides.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
            # Override direct en constructeur : prioritaire sur le .env chargé
            # par pydantic-settings (qui contient un SMTP_HOST local non vide).
            init_kwargs[key.lower()] = None
        else:
            monkeypatch.setenv(key, value)
    return Settings(**init_kwargs)


def test_production_settings_boot_without_smtp_host(_clean_settings_cache, monkeypatch) -> None:
    settings = _build_settings(monkeypatch, SMTP_HOST=None)

    assert settings.environment == "production"
    assert settings.smtp_host is None


def test_production_settings_boot_without_stripe_billing_disabled(_clean_settings_cache, monkeypatch) -> None:
    for key in ("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET", "STRIPE_PRICE_DEMO", "STRIPE_PRICE_PROFESSIONAL", "STRIPE_PRICE_ENTERPRISE"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("AUTH_JWT_SECRET", "prod-jwt-secret-0123456789abcdef0123")

    from backend.app.config.settings import Settings

    settings = Settings()

    assert settings.environment == "production"
    assert settings.billing_enabled is False


def test_billing_enabled_true_only_when_stripe_fully_configured(_clean_settings_cache, monkeypatch) -> None:
    settings = _build_settings(monkeypatch)
    assert settings.billing_enabled is True

    partial = _build_settings(monkeypatch, STRIPE_WEBHOOK_SECRET=None)
    assert partial.billing_enabled is False


def test_billing_provider_returns_clear_503_when_stripe_missing(_clean_settings_cache, monkeypatch) -> None:
    from fastapi import HTTPException
    import backend.app.dependencies.billing as billing_dep

    # Construire un settings Stripe-vide en neutralisant l'env ET le .env local
    # (pydantic-settings priorise le .env sur un kwargs None).
    for key in ("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET", "STRIPE_PRICE_DEMO", "STRIPE_PRICE_PROFESSIONAL", "STRIPE_PRICE_ENTERPRISE"):
        monkeypatch.setenv(key, "")
    monkeypatch.setenv("ENVIRONMENT", "production")
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
