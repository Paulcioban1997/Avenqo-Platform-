from uuid import uuid4
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from backend.app.models import Base, Company
from backend.app.models.crm import CRMCalendarConnection
from backend.app.services.connector_secret_cipher import ConnectorSecretCipher, ConnectorSecretError
from backend.app.services.calendar_fixture_repair import repair_revoked_calendar_fixture


def test_revoked_fixture_is_preserved_encrypted_and_disconnected():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    cipher = ConnectorSecretCipher([Fernet.generate_key().decode()])
    with Session(engine) as db:
        company = Company(id=uuid4(), name="Isolated fixture", slug="tenant-alpha-isolated", email="fixture@example.invalid", country="CA", timezone="America/Toronto", industry="Test", subscription_plan="base")
        db.add(company); db.flush()
        row = CRMCalendarConnection(company_id=company.id, provider="google", account_email="revoked@example.invalid",
                                    sync_status="disconnected", encrypted_credentials="revoked_fake_payload")
        db.add(row); db.flush()
        with pytest.raises(ConnectorSecretError, match="sandbox-only"):
            repair_revoked_calendar_fixture(db, row.id, cipher, environment="production")
        assert repair_revoked_calendar_fixture(db, row.id, cipher, environment="sandbox")
        payload = cipher.decrypt(row.encrypted_credentials)
        assert payload == {"revoked": True, "reauthorization_required": True, "legacy_fixture": "revoked_fake_payload"}
        assert "access_token" not in payload and row.sync_status == "disconnected"
        assert not repair_revoked_calendar_fixture(db, row.id, cipher, environment="sandbox")


def test_unknown_credentials_or_active_calendar_are_never_replaced():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    cipher = ConnectorSecretCipher([Fernet.generate_key().decode()])
    with Session(engine) as db:
        company = Company(id=uuid4(), name="Isolated fixture", slug="tenant-alpha-isolated", email="fixture@example.invalid", country="CA", timezone="America/Toronto", industry="Test", subscription_plan="base")
        db.add(company); db.flush()
        row = CRMCalendarConnection(company_id=company.id, provider="google", account_email="test@example.invalid",
                                    sync_status="connected", encrypted_credentials="revoked_fake_payload")
        db.add(row); db.flush()
        with pytest.raises(ConnectorSecretError):
            repair_revoked_calendar_fixture(db, row.id, cipher, environment="sandbox")
        row.sync_status = "disconnected"; row.encrypted_credentials = "unknown-corrupt-value"
        with pytest.raises(ConnectorSecretError):
            repair_revoked_calendar_fixture(db, row.id, cipher, environment="sandbox")
        assert row.encrypted_credentials == "unknown-corrupt-value"
