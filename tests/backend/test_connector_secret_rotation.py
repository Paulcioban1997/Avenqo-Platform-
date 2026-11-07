from uuid import uuid4
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.models import Base
from backend.app.models.commerce_connection import CommerceConnection
from backend.app.models.crm import CRMCalendarConnection
from backend.app.services.connector_secret_cipher import ConnectorSecretCipher, ConnectorSecretError
from backend.app.services.connector_secret_rotation import rotate_connector_secrets


def fixture_store(db, cipher):
    company = uuid4()
    rows = [CommerceConnection(company_id=company, provider="shopify", external_account_id="test-account",
                              encrypted_credentials=cipher.encrypt({"marker": "commerce-test"})),
            CRMCalendarConnection(company_id=company, provider="google", account_email="test@example.invalid",
                                  encrypted_credentials=cipher.encrypt({"marker": "calendar-test"}))]
    db.add_all(rows); db.commit()
    return rows


def test_dry_run_then_verified_rotation_of_both_stores():
    old, new = (Fernet.generate_key().decode() for _ in range(2))
    engine = create_engine("sqlite:///:memory:"); Base.metadata.create_all(engine)
    with Session(engine) as db:
        rows = fixture_store(db, ConnectorSecretCipher([old]))
        original = [r.encrypted_credentials for r in rows]
        hybrid = ConnectorSecretCipher([new, old])
        assert rotate_connector_secrets(db, hybrid)["needs_rotation"] == 2
        db.rollback(); db.expire_all()
        assert [r.encrypted_credentials for r in rows] == original
        report = rotate_connector_secrets(db, hybrid, apply=True); db.commit(); db.expire_all()
        assert report["rotated"] == report["verified"] == 2
        primary = ConnectorSecretCipher([new])
        assert primary.decrypt(rows[0].encrypted_credentials) == {"marker": "commerce-test"}
        assert primary.decrypt(rows[1].encrypted_credentials) == {"marker": "calendar-test"}
        for before, after in zip(original, (r.encrypted_credentials for r in rows)):
            assert Fernet(old.encode()).extract_timestamp(before.encode()) == Fernet(new.encode()).extract_timestamp(after.encode())
            with pytest.raises(ConnectorSecretError):
                ConnectorSecretCipher([old]).decrypt(after)
        assert rotate_connector_secrets(db, hybrid, apply=True)["rotated"] == 0


def test_failed_rotation_rolls_back_all_prior_changes():
    old, new, unrelated = (Fernet.generate_key().decode() for _ in range(3))
    engine = create_engine("sqlite:///:memory:"); Base.metadata.create_all(engine)
    with Session(engine) as db:
        rows = fixture_store(db, ConnectorSecretCipher([old]))
        rows[1].encrypted_credentials = ConnectorSecretCipher([unrelated]).encrypt({"marker": "unreadable-test"})
        db.commit(); original = rows[0].encrypted_credentials
        with pytest.raises(ConnectorSecretError):
            rotate_connector_secrets(db, ConnectorSecretCipher([new, old]), apply=True)
        db.rollback(); db.expire_all()
        assert rows[0].encrypted_credentials == original


def test_rotation_key_list_accepts_json_and_csv_without_reordering():
    import json
    from backend.app.config.settings import Settings
    keys = [Fernet.generate_key().decode(), Fernet.generate_key().decode()]
    assert Settings.parse_string_list(json.dumps(keys)) == keys
    assert Settings.parse_string_list(",".join(keys)) == keys
