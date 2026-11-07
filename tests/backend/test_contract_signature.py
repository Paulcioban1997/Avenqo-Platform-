from uuid import uuid4
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.models.base import Base
from backend.app.models.audit_log import AuditLogEntry
from backend.app.services.audit_log_service import AuditLogService
from backend.app.services.contract_signature_service import (
    AVAILABLE_CONTRACTS,
    ContractSignatureService,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_get_contract_templates_fr_and_en(db_session):
    service = ContractSignatureService(db_session)

    # SaaS Contract FR & EN
    saas_fr = service.get_template("SAAS_SUBSCRIPTION", language="fr")
    assert saas_fr["contract_type"] == "SAAS_SUBSCRIPTION"
    assert saas_fr["language"] == "fr"
    assert "PMC SOLUTIONS AI INC." in saas_fr["content"]
    assert len(saas_fr["sha256"]) == 64

    saas_en = service.get_template("SAAS_SUBSCRIPTION", language="en")
    assert saas_en["language"] == "en"
    assert "PMC SOLUTIONS AI INC." in saas_en["content"]
    assert saas_en["sha256"] != saas_fr["sha256"]

    # Private License Contract FR & EN (Non-Exclusive by default)
    lic_fr = service.get_template("PRIVATE_LICENSE", language="fr")
    assert "STRICTEMENT NON EXCLUSIF" in lic_fr["content"]
    assert lic_fr["contract_type"] == "PRIVATE_LICENSE"

    lic_en = service.get_template("PRIVATE_LICENSE", language="en")
    assert "NON-EXCLUSIVE BASIS" in lic_en["content"]
    assert lic_en["contract_type"] == "PRIVATE_LICENSE"


def test_sign_contract_requires_explicit_consent(db_session):
    service = ContractSignatureService(db_session)
    company_id = uuid4()
    user_id = uuid4()

    with pytest.raises(ValueError, match="consentement exprès"):
        service.sign_contract(
            company_id=company_id,
            user_id=user_id,
            user_email="client@example.ca",
            user_name="Jean Dupont",
            contract_type="SAAS_SUBSCRIPTION",
            consent_checkbox=False,
        )


def test_sign_contract_success_with_audit_trail_and_archive(db_session):
    service = ContractSignatureService(db_session)
    company_id = uuid4()
    user_id = uuid4()

    receipt = service.sign_contract(
        company_id=company_id,
        user_id=user_id,
        user_email="francis@produits-ero.ca",
        user_name="Francis Queval",
        contract_type="PRIVATE_LICENSE",
        language="fr",
        ip_address="192.168.1.100",
        user_agent="Mozilla/5.0 TestBrowser",
        consent_checkbox=True,
    )

    assert receipt["company_id"] == str(company_id)
    assert receipt["user_id"] == str(user_id)
    assert receipt["signer_email"] == "francis@produits-ero.ca"
    assert receipt["contract_type"] == "PRIVATE_LICENSE"
    assert receipt["status"] == "SIGNED_LEGALLY_BINDING_DRAFT"
    assert len(receipt["contract_sha256"]) == 64

    # Verify audit log entry in database
    from uuid import UUID
    audit_entry = db_session.query(AuditLogEntry).filter(AuditLogEntry.id == UUID(receipt["audit_entry_id"])).first()
    assert audit_entry is not None
    assert audit_entry.action == "contract.digitally_signed"
    assert audit_entry.target_type == "commercial_contract"
    assert audit_entry.company_id == company_id
    assert audit_entry.safe_metadata["signer_email"] == "francis@produits-ero.ca"
    assert audit_entry.safe_metadata["contract_type"] == "PRIVATE_LICENSE"
    assert audit_entry.safe_metadata["legal_framework"] == "RLRQ c. C-1.1 (Québec)"
