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


def test_production_settings_still_require_stripe(_clean_settings_cache, monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("AUTH_JWT_SECRET", "prod-jwt-secret-0123456789abcdef0123")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("STRIPE_PRICE_DEMO", raising=False)
    monkeypatch.delenv("STRIPE_PRICE_PROFESSIONAL", raising=False)
    monkeypatch.delenv("STRIPE_PRICE_ENTERPRISE", raising=False)

    from backend.app.config.settings import Settings

    with pytest.raises(Exception, match="Stripe"):
        Settings()


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
