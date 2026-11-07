from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.models import Base, Company
from backend.app.models.commerce_connection import CommerceConnection
from backend.app.models.crm import CRMCalendarConnection
from backend.app.services.connector_key_rotation import (
    UNDECRYPTABLE,
    ConnectorKeyRotationService,
    generate_connector_key,
    key_fingerprint,
)
from backend.app.services.connector_secret_cipher import ConnectorSecretCipher, ConnectorSecretError
from scripts import rotate_connector_keys


def _key() -> str:
    return Fernet.generate_key().decode("ascii")


@pytest.fixture
def factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'rotation.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _company(session, name: str) -> Company:
    company = Company(
        name=name,
        slug=f"{name.lower()}-{uuid4().hex[:6]}",
        email=f"{uuid4().hex}@example.com",
        country="Canada",
        timezone="America/Toronto",
        industry="Retail",
        subscription_plan="base",
    )
    session.add(company)
    session.flush()
    return company


def _seed(session, old_key: str) -> dict[str, dict]:
    old = ConnectorSecretCipher([old_key])
    company_a, company_b = _company(session, "Alpha"), _company(session, "Beta")
    expected: dict[str, dict] = {}
    for company, provider, secret in (
        (company_a, "woocommerce", {"consumer_key": "ck_a", "consumer_secret": "cs_a"}),
        (company_b, "shopify", {"access_token": "shpat_b", "refresh_token": "shprt_b"}),
    ):
        row = CommerceConnection(
            company_id=company.id,
            provider=provider,
            external_account_id=f"{provider}-{company.slug}",
            encrypted_credentials=old.encrypt(secret),
        )
        session.add(row)
        session.flush()
        expected[str(row.id)] = secret
    session.add(
        CommerceConnection(
            company_id=company_a.id, provider="shopify", external_account_id="disconnected", encrypted_credentials=None
        )
    )
    calendar = CRMCalendarConnection(
        company_id=company_a.id,
        provider="google",
        account_email="agenda@example.com",
        encrypted_credentials=old.encrypt({"refresh_token": "g_refresh"}),
    )
    session.add(calendar)
    session.flush()
    expected[str(calendar.id)] = {"refresh_token": "g_refresh"}
    session.commit()
    return expected


def _all_tokens(session) -> dict[str, str]:
    tokens = {}
    for model in (CommerceConnection, CRMCalendarConnection):
        for row in session.scalars(select(model).where(model.encrypted_credentials.is_not(None))):
            tokens[str(row.id)] = row.encrypted_credentials
    return tokens


def test_generated_key_is_valid_fernet_and_fingerprint_hides_it() -> None:
    key = generate_connector_key()
    Fernet(key.encode("ascii"))
    fingerprint = key_fingerprint(key)
    assert len(fingerprint) == 12
    assert fingerprint not in key
    assert key_fingerprint(key) == fingerprint


def test_rejects_missing_duplicate_or_invalid_keys(factory) -> None:
    key = _key()
    with factory() as session:
        with pytest.raises(ConnectorSecretError, match="not configured"):
            ConnectorKeyRotationService(session, [])
        with pytest.raises(ConnectorSecretError, match="duplicates"):
            ConnectorKeyRotationService(session, [key, key])
        with pytest.raises(ConnectorSecretError, match="invalid"):
            ConnectorKeyRotationService(session, ["not-a-key"])


def test_dry_run_reports_without_writing(factory) -> None:
    old, new = _key(), _key()
    with factory() as session:
        _seed(session, old)
        before = _all_tokens(session)
        report = ConnectorKeyRotationService(session, [new, old]).rotate(dry_run=True)
        session.expire_all()
        assert _all_tokens(session) == before
    assert report.dry_run is True
    assert sum(t.rotated for t in report.tables) == 3
    assert report.safe_to_retire_previous_keys is False


def test_full_rotation_lifecycle_preserves_every_credential(factory) -> None:
    old, new = _key(), _key()
    with factory() as session:
        expected = _seed(session, old)

        status = ConnectorKeyRotationService(session, [new, old]).status()
        assert status.not_on_primary == 3
        assert all(key_fingerprint(old) in t.by_key for t in status.tables)

        report = ConnectorKeyRotationService(session, [new, old]).rotate(dry_run=False, batch_size=1)
        assert report.failed == 0
        assert sum(t.rotated for t in report.tables) == 3

        verify = ConnectorKeyRotationService(session, [new, old]).status()
        assert verify.safe_to_retire_previous_keys is True

        session.expire_all()
        new_only = ConnectorSecretCipher([new])
        for row_id, token in _all_tokens(session).items():
            assert new_only.decrypt(token) == expected[row_id]
        with pytest.raises(ConnectorSecretError):
            ConnectorSecretCipher([old]).decrypt(next(iter(_all_tokens(session).values())))


def test_rotation_is_idempotent_and_resumable(factory) -> None:
    old, new = _key(), _key()
    with factory() as session:
        _seed(session, old)
        service = ConnectorKeyRotationService(session, [new, old])
        service.rotate(dry_run=False)
        session.expire_all()
        snapshot = _all_tokens(session)
        second = service.rotate(dry_run=False)
        session.expire_all()
        assert sum(t.rotated for t in second.tables) == 0
        assert _all_tokens(session) == snapshot


def test_rollback_by_reordering_keys_restores_old_primary(factory) -> None:
    old, new = _key(), _key()
    with factory() as session:
        expected = _seed(session, old)
        ConnectorKeyRotationService(session, [new, old]).rotate(dry_run=False)
        rollback = ConnectorKeyRotationService(session, [old, new]).rotate(dry_run=False)
        assert sum(t.rotated for t in rollback.tables) == 3
        session.expire_all()
        old_only = ConnectorSecretCipher([old])
        for row_id, token in _all_tokens(session).items():
            assert old_only.decrypt(token) == expected[row_id]


def test_undecryptable_rows_block_retirement_and_are_left_untouched(factory) -> None:
    old, new, lost = _key(), _key(), _key()
    with factory() as session:
        _seed(session, old)
        company = _company(session, "Gamma")
        orphan = CommerceConnection(
            company_id=company.id,
            provider="woocommerce",
            external_account_id="orphan",
            encrypted_credentials=ConnectorSecretCipher([lost]).encrypt({"consumer_key": "ck_lost"}),
        )
        session.add(orphan)
        session.commit()
        original = orphan.encrypted_credentials

        report = ConnectorKeyRotationService(session, [new, old]).rotate(dry_run=False)
        assert str(orphan.id) in [i for t in report.tables for i in t.failed_ids]
        session.expire_all()
        assert session.get(CommerceConnection, orphan.id).encrypted_credentials == original

        verify = ConnectorKeyRotationService(session, [new, old]).status()
        assert verify.undecryptable == 1
        assert verify.tables[0].by_key[UNDECRYPTABLE] == 1
        assert verify.safe_to_retire_previous_keys is False


def test_cli_verify_exit_codes_and_never_prints_keys(factory, monkeypatch, capsys) -> None:
    old, new = _key(), _key()
    with factory() as session:
        _seed(session, old)
    monkeypatch.setattr(rotate_connector_keys, "_session", lambda: factory())
    monkeypatch.setenv("CONNECTOR_ENCRYPTION_KEYS", f"{new},{old}")

    assert rotate_connector_keys.main(["verify"]) == 2
    assert rotate_connector_keys.main(["rotate"]) == 0
    assert rotate_connector_keys.main(["verify"]) == 2
    monkeypatch.setenv("ENVIRONMENT", "test")
    assert rotate_connector_keys.main(["rotate", "--apply"]) == 2
    assert rotate_connector_keys.main(["rotate", "--apply", "--confirm-environment", "test"]) == 0
    assert rotate_connector_keys.main(["verify"]) == 0

    output = capsys.readouterr()
    combined = output.out + output.err
    assert old not in combined and new not in combined
    assert key_fingerprint(new) in combined


def test_cli_accepts_json_and_masks_connection_errors(monkeypatch, capsys):
    import json
    key = _key()
    monkeypatch.setenv("CONNECTOR_ENCRYPTION_KEYS", json.dumps([key]))
    assert rotate_connector_keys._keys_from_env() == [key]
    def fail():
        raise RuntimeError(key)
    monkeypatch.setattr(rotate_connector_keys, "_session", fail)
    assert rotate_connector_keys.main(["status"]) == 1
    assert rotate_connector_keys.main(["generate"]) == 2
    captured = capsys.readouterr()
    assert key not in captured.out + captured.err
