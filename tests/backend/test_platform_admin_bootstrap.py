"""Remédiation finale V1 — bootstrap sécurisé du compte `platform_admin`.

Couvre `scripts/set_platform_admin.py` : ne fait jamais que promouvoir un
compte EXISTANT (jamais de création silencieuse, jamais de mot de passe par
défaut), écrit une entrée d'audit, et refuse les cas invalides.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import scripts.set_platform_admin as set_platform_admin_module
from backend.app.models import AuditLogEntry, Base, Company, CompanyStatus, User, UserRole


@pytest.fixture
def session_factory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'admin_bootstrap.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(set_platform_admin_module, "SessionLocal", factory)
    return factory


def _create_user(factory, *, email: str, is_platform_admin: bool = False) -> None:
    with factory() as session:
        company = Company(
            name="Acme", slug=f"acme-{uuid4().hex[:8]}", email=f"acme-{uuid4().hex[:8]}@example.com",
            country="CA", timezone="America/Toronto", industry="Retail",
            subscription_plan="demo", status=CompanyStatus.ACTIVE,
        )
        session.add(company)
        session.flush()
        user = User(
            company_id=company.id, first_name="Dana", last_name="Owner", email=email,
            password_hash="hash", role=UserRole.OWNER, is_active=True,
            is_platform_admin=is_platform_admin,
        )
        session.add(user)
        session.commit()


def test_promotes_existing_user_to_platform_admin(session_factory) -> None:
    _create_user(session_factory, email="owner@example.com")

    user = set_platform_admin_module.set_platform_admin("owner@example.com")

    assert user.is_platform_admin is True
    with session_factory() as session:
        refreshed = session.scalar(select(User).where(User.email == "owner@example.com"))
        assert refreshed.is_platform_admin is True


def test_writes_audit_entry_when_promoting(session_factory) -> None:
    _create_user(session_factory, email="owner2@example.com")

    user = set_platform_admin_module.set_platform_admin("owner2@example.com")

    with session_factory() as session:
        entries = session.scalars(select(AuditLogEntry)).all()
        assert len(entries) == 1
        assert entries[0].action == "platform_admin_granted"
        assert entries[0].actor_user_id == user.id
        assert entries[0].safe_metadata["email"] == "owner2@example.com"


def test_refuses_to_promote_nonexistent_user(session_factory) -> None:
    with pytest.raises(ValueError, match="Aucun compte existant"):
        set_platform_admin_module.set_platform_admin("ghost@example.com")


def test_refuses_to_promote_already_platform_admin(session_factory) -> None:
    _create_user(session_factory, email="already-admin@example.com", is_platform_admin=True)

    with pytest.raises(ValueError, match="déjà platform_admin"):
        set_platform_admin_module.set_platform_admin("already-admin@example.com")


def test_never_creates_a_new_user_silently(session_factory) -> None:
    with pytest.raises(ValueError):
        set_platform_admin_module.set_platform_admin("nobody@example.com")

    with session_factory() as session:
        assert session.scalar(select(User).where(User.email == "nobody@example.com")) is None
