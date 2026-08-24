"""FINAL V1 — bootstrap sécurisé du platform_admin propriétaire d'Avenqo.

Couvre `scripts/bootstrap_platform_admin.py` : lit des identifiants
synthétiques (JAMAIS les vrais identifiants du propriétaire) depuis un objet
`settings` simulé, crée le compte une seule fois, confirme sans dupliquer à
la relance, et n'expose jamais le mot de passe ni son hash.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import scripts.bootstrap_platform_admin as bootstrap_module
from backend.app.models import AuditLogEntry, Base, Company, User

_TEST_EMAIL = "owner-test@example.com"
_TEST_PASSWORD = "Sup3r!SecretTest"


@pytest.fixture
def session_factory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'platform_admin_bootstrap.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(bootstrap_module, "SessionLocal", factory)
    return factory


def _use_settings(monkeypatch: pytest.MonkeyPatch, *, email: str | None, password: str | None) -> None:
    fake_settings = SimpleNamespace(platform_admin_email=email, platform_admin_password=password)
    monkeypatch.setattr(bootstrap_module, "get_settings", lambda: fake_settings)


def test_creates_platform_admin_and_internal_company_on_first_run(session_factory, monkeypatch) -> None:
    _use_settings(monkeypatch, email=_TEST_EMAIL, password=_TEST_PASSWORD)

    user, created = bootstrap_module.bootstrap_platform_admin()

    assert created is True
    assert user.is_platform_admin is True
    assert user.email == _TEST_EMAIL
    assert user.password_hash != _TEST_PASSWORD
    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.slug == "avenqo-platform"))
        assert company is not None
        refreshed = session.scalar(select(User).where(User.email == _TEST_EMAIL))
        assert refreshed.is_platform_admin is True


def test_second_run_is_idempotent_no_duplicate(session_factory, monkeypatch) -> None:
    _use_settings(monkeypatch, email=_TEST_EMAIL, password=_TEST_PASSWORD)
    bootstrap_module.bootstrap_platform_admin()

    user, created = bootstrap_module.bootstrap_platform_admin()

    assert created is False
    assert user.is_platform_admin is True
    with session_factory() as session:
        users = session.scalars(select(User).where(User.email == _TEST_EMAIL)).all()
        assert len(users) == 1
        companies = session.scalars(select(Company).where(Company.slug == "avenqo-platform")).all()
        assert len(companies) == 1


def test_writes_audit_entry_on_each_run(session_factory, monkeypatch) -> None:
    _use_settings(monkeypatch, email=_TEST_EMAIL, password=_TEST_PASSWORD)

    bootstrap_module.bootstrap_platform_admin()
    bootstrap_module.bootstrap_platform_admin()

    with session_factory() as session:
        entries = session.scalars(select(AuditLogEntry)).all()
        assert [entry.action for entry in entries] == [
            "platform_admin_bootstrapped",
            "platform_admin_confirmed",
        ]
        assert all(_TEST_PASSWORD not in str(entry.safe_metadata) for entry in entries)


def test_never_makes_platform_admin_a_member_of_an_existing_tenant(session_factory, monkeypatch) -> None:
    _use_settings(monkeypatch, email=_TEST_EMAIL, password=_TEST_PASSWORD)
    with session_factory() as session:
        from backend.app.models import CompanyStatus

        tenant = Company(
            name="Acme", slug="acme", email="acme@example.com", country="CA",
            timezone="America/Toronto", industry="Retail", subscription_plan="demo",
            status=CompanyStatus.ACTIVE,
        )
        session.add(tenant)
        session.commit()

    user, _ = bootstrap_module.bootstrap_platform_admin()

    with session_factory() as session:
        tenant = session.scalar(select(Company).where(Company.slug == "acme"))
        assert user.company_id != tenant.id


def test_refuses_when_email_not_configured(session_factory, monkeypatch) -> None:
    _use_settings(monkeypatch, email=None, password=_TEST_PASSWORD)

    with pytest.raises(bootstrap_module.BootstrapError, match="PLATFORM_ADMIN_EMAIL"):
        bootstrap_module.bootstrap_platform_admin()


def test_refuses_when_password_not_configured(session_factory, monkeypatch) -> None:
    _use_settings(monkeypatch, email=_TEST_EMAIL, password=None)

    with pytest.raises(bootstrap_module.BootstrapError, match="PLATFORM_ADMIN_PASSWORD"):
        bootstrap_module.bootstrap_platform_admin()


def test_refuses_weak_password(session_factory, monkeypatch) -> None:
    _use_settings(monkeypatch, email=_TEST_EMAIL, password="weak")

    with pytest.raises(bootstrap_module.BootstrapError):
        bootstrap_module.bootstrap_platform_admin()
