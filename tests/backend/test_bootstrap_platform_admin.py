"""FINAL V1 — bootstrap sécurisé du platform_admin propriétaire d'Avenqo.

Couvre `scripts/bootstrap_platform_admin.py` : lit des identifiants
synthétiques (JAMAIS les vrais identifiants du propriétaire) depuis un objet
`settings` simulé, crée le compte une seule fois, confirme sans dupliquer à
la relance, et n'expose jamais le mot de passe ni son hash.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import scripts.bootstrap_platform_admin as bootstrap_module
from backend.app.core.security import hash_token, verify_password
from backend.app.models import AuditLogEntry, AuthSession, Base, BillingAccount, Company, User

_TEST_EMAIL = "owner-test@example.com"
_TEST_PASSWORD = "Sup3r!SecretTest"
_ROTATED_PASSWORD = "Rot@ted!SecretTest2"


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
        billing = session.scalar(
            select(BillingAccount).where(BillingAccount.company_id == company.id)
        )
        assert billing is not None
        assert billing.plan_code == "enterprise"
        assert billing.status == "active"


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
        billing_accounts = session.scalars(
            select(BillingAccount).where(BillingAccount.company_id == user.company_id)
        ).all()
        assert len(billing_accounts) == 1


def test_refuses_to_elevate_configured_email_inside_customer_tenant(
    session_factory,
    monkeypatch,
) -> None:
    _use_settings(monkeypatch, email=_TEST_EMAIL, password=_TEST_PASSWORD)
    with session_factory() as session:
        from backend.app.models import CompanyStatus, UserRole

        tenant = Company(
            name="Acme",
            slug="acme",
            email="acme@example.com",
            country="CA",
            timezone="America/Toronto",
            industry="Retail",
            subscription_plan="demo",
            status=CompanyStatus.ACTIVE,
        )
        session.add(tenant)
        session.flush()
        session.add(
            User(
                company_id=tenant.id,
                first_name="Tenant",
                last_name="Owner",
                email=_TEST_EMAIL,
                password_hash="unchanged",
                role=UserRole.OWNER,
                is_platform_admin=False,
            )
        )
        session.commit()

    with pytest.raises(bootstrap_module.BootstrapError, match="Avenqo Platform"):
        bootstrap_module.bootstrap_platform_admin()

    with session_factory() as session:
        user = session.scalar(select(User).where(User.email == _TEST_EMAIL))
        assert user.is_platform_admin is False
        assert session.scalar(select(BillingAccount)) is None


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


def _add_active_session(session_factory, user_id) -> None:
    now = datetime.now(timezone.utc)
    with session_factory() as session:
        session.add(
            AuthSession(
                id=uuid4(),
                user_id=user_id,
                token_hash=hash_token(f"token-{uuid4()}"),
                created_at=now,
                expires_at=now + timedelta(days=30),
            )
        )
        session.commit()


def test_normal_bootstrap_confirms_role_without_touching_password(session_factory, monkeypatch) -> None:
    """A. Existing platform admin + normal bootstrap → role confirmed, password untouched."""
    _use_settings(monkeypatch, email=_TEST_EMAIL, password=_TEST_PASSWORD)
    bootstrap_module.bootstrap_platform_admin()
    with session_factory() as session:
        original_hash = session.scalar(select(User).where(User.email == _TEST_EMAIL)).password_hash

    _use_settings(monkeypatch, email=_TEST_EMAIL, password=_ROTATED_PASSWORD)
    user, created = bootstrap_module.bootstrap_platform_admin()

    assert created is False
    assert user.is_platform_admin is True
    with session_factory() as session:
        refreshed = session.scalar(select(User).where(User.email == _TEST_EMAIL))
        assert refreshed.password_hash == original_hash
        assert verify_password(_TEST_PASSWORD, refreshed.password_hash)


def test_sync_password_rotates_existing_admin_credentials(session_factory, monkeypatch) -> None:
    """B. Existing platform admin + explicit password sync → new password works."""
    _use_settings(monkeypatch, email=_TEST_EMAIL, password=_TEST_PASSWORD)
    bootstrap_module.bootstrap_platform_admin()

    _use_settings(monkeypatch, email=_TEST_EMAIL, password=_ROTATED_PASSWORD)
    user, created = bootstrap_module.sync_platform_admin_password()

    assert created is False
    with session_factory() as session:
        refreshed = session.scalar(select(User).where(User.email == _TEST_EMAIL))
        assert verify_password(_ROTATED_PASSWORD, refreshed.password_hash)


def test_sync_password_invalidates_previous_password(session_factory, monkeypatch) -> None:
    """C. Previous password stops working after sync."""
    _use_settings(monkeypatch, email=_TEST_EMAIL, password=_TEST_PASSWORD)
    bootstrap_module.bootstrap_platform_admin()

    _use_settings(monkeypatch, email=_TEST_EMAIL, password=_ROTATED_PASSWORD)
    bootstrap_module.sync_platform_admin_password()

    with session_factory() as session:
        refreshed = session.scalar(select(User).where(User.email == _TEST_EMAIL))
        assert not verify_password(_TEST_PASSWORD, refreshed.password_hash)


def test_sync_password_revokes_existing_auth_sessions(session_factory, monkeypatch) -> None:
    """D. Existing auth sessions are revoked after admin password rotation."""
    _use_settings(monkeypatch, email=_TEST_EMAIL, password=_TEST_PASSWORD)
    user, _ = bootstrap_module.bootstrap_platform_admin()
    _add_active_session(session_factory, user.id)
    _add_active_session(session_factory, user.id)

    _use_settings(monkeypatch, email=_TEST_EMAIL, password=_ROTATED_PASSWORD)
    bootstrap_module.sync_platform_admin_password()

    with session_factory() as session:
        sessions = session.scalars(select(AuthSession).where(AuthSession.user_id == user.id)).all()
        assert len(sessions) == 2
        assert all(item.revoked_at is not None for item in sessions)


def test_sync_password_keeps_admin_active_and_verified(session_factory, monkeypatch) -> None:
    """E. Admin remains is_platform_admin=True, is_active=True, email verified."""
    _use_settings(monkeypatch, email=_TEST_EMAIL, password=_TEST_PASSWORD)
    bootstrap_module.bootstrap_platform_admin()
    with session_factory() as session:
        stale = session.scalar(select(User).where(User.email == _TEST_EMAIL))
        stale.is_active = False
        stale.email_verified_at = None
        session.commit()

    _use_settings(monkeypatch, email=_TEST_EMAIL, password=_ROTATED_PASSWORD)
    user, _ = bootstrap_module.sync_platform_admin_password()

    assert user.is_platform_admin is True
    assert user.is_active is True
    assert user.email_verified_at is not None


def test_sync_password_does_not_touch_normal_tenant_users(session_factory, monkeypatch) -> None:
    """F. Normal tenant user passwords are untouched by the platform-admin sync."""
    from backend.app.core.security import hash_password
    from backend.app.models import CompanyStatus, UserRole

    tenant_password_hash = hash_password("TenantUser!Pass1")
    with session_factory() as session:
        tenant = Company(
            name="Acme", slug="acme", email="acme@example.com", country="CA",
            timezone="America/Toronto", industry="Retail", subscription_plan="demo",
            status=CompanyStatus.ACTIVE,
        )
        session.add(tenant)
        session.flush()
        tenant_user = User(
            company=tenant, first_name="Tenant", last_name="User",
            email="tenant-user@example.com", password_hash=tenant_password_hash,
            role=UserRole.OWNER, is_active=True, is_platform_admin=False,
            email_verified_at=datetime.now(timezone.utc),
        )
        session.add(tenant_user)
        session.commit()
        tenant_user_id = tenant_user.id

    _use_settings(monkeypatch, email=_TEST_EMAIL, password=_TEST_PASSWORD)
    bootstrap_module.sync_platform_admin_password()

    with session_factory() as session:
        refreshed_tenant_user = session.get(User, tenant_user_id)
        assert refreshed_tenant_user.password_hash == tenant_password_hash
        assert refreshed_tenant_user.is_platform_admin is False


def test_sync_password_never_logs_secret_material(session_factory, monkeypatch, capsys) -> None:
    """G. Password/hash is never emitted in command output or audit metadata."""
    _use_settings(monkeypatch, email=_TEST_EMAIL, password=_TEST_PASSWORD)
    bootstrap_module.bootstrap_platform_admin()

    _use_settings(monkeypatch, email=_TEST_EMAIL, password=_ROTATED_PASSWORD)
    user, _ = bootstrap_module.sync_platform_admin_password()
    exit_code = bootstrap_module.main(["--sync-password"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert _TEST_PASSWORD not in captured.out
    assert _ROTATED_PASSWORD not in captured.out
    assert user.password_hash not in captured.out
    with session_factory() as session:
        entries = session.scalars(select(AuditLogEntry)).all()
        for entry in entries:
            metadata_text = str(entry.safe_metadata)
            assert _TEST_PASSWORD not in metadata_text
            assert _ROTATED_PASSWORD not in metadata_text
            assert user.password_hash not in metadata_text


def test_sync_password_writes_distinct_audit_action(session_factory, monkeypatch) -> None:
    _use_settings(monkeypatch, email=_TEST_EMAIL, password=_TEST_PASSWORD)
    bootstrap_module.bootstrap_platform_admin()

    _use_settings(monkeypatch, email=_TEST_EMAIL, password=_ROTATED_PASSWORD)
    bootstrap_module.sync_platform_admin_password()

    with session_factory() as session:
        entries = session.scalars(select(AuditLogEntry)).all()
        assert [entry.action for entry in entries] == [
            "platform_admin_bootstrapped",
            "platform_admin_password_synced",
        ]


def test_sync_password_creates_account_when_missing(session_factory, monkeypatch) -> None:
    _use_settings(monkeypatch, email=_TEST_EMAIL, password=_TEST_PASSWORD)

    user, created = bootstrap_module.sync_platform_admin_password()

    assert created is True
    assert user.is_platform_admin is True
    assert verify_password(_TEST_PASSWORD, user.password_hash)


def test_default_cli_invocation_does_not_sync_password(session_factory, monkeypatch) -> None:
    _use_settings(monkeypatch, email=_TEST_EMAIL, password=_TEST_PASSWORD)
    bootstrap_module.main([])
    with session_factory() as session:
        original_hash = session.scalar(select(User).where(User.email == _TEST_EMAIL)).password_hash

    _use_settings(monkeypatch, email=_TEST_EMAIL, password=_ROTATED_PASSWORD)
    exit_code = bootstrap_module.main([])

    assert exit_code == 0
    with session_factory() as session:
        refreshed = session.scalar(select(User).where(User.email == _TEST_EMAIL))
        assert refreshed.password_hash == original_hash
