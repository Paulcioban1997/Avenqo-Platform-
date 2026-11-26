from datetime import datetime, timezone
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select
from backend.app.models import TenantDocument
from backend.app.models.accounting import AccountingInvoice
from backend.app.services.document_ai_service import DocumentAIService
from backend.app.routers import accounting
from shared.ai_engine.contracts import TenantContext
"""Accounting must follow the same tenant-scoped active source as Data Hub / Retail."""


from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.models.accounting import AccountingInvoice, AccountingTransaction
from backend.app.models.base import Base, DatasetStatus, UserRole
from backend.app.models.company import Company
from backend.app.models.dataset import Dataset
from backend.app.models.mapping import Mapping
from backend.app.models.user import User
from backend.app.services.accounting_intelligence_service import AccountingIntelligenceService
from backend.app.services.accounting_source_scope import resolve_accounting_dataset_scope
from backend.app.services.retail_source_service import RetailSourceService
from shared.ai_engine.contracts import TenantContext


@pytest.fixture
def db_session(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'accounting_source.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        yield session


def _company(session, slug: str) -> Company:
    company = Company(
        id=uuid4(),
        name=f"Company {slug}",
        slug=slug,
        email=f"{slug}@example.com",
        country="CA",
        timezone="America/Toronto",
        industry="Retail",
        subscription_plan="professional",
    )
    session.add(company)
    session.flush()
    return company


def _user(session, company: Company) -> User:
    user = User(
        id=uuid4(),
        company_id=company.id,
        email=f"owner-{company.slug}@example.com",
        password_hash="x",
        first_name="Owner",
        last_name="Test",
        role=UserRole.OWNER,
        is_active=True,
        email_verified_at=datetime.now(timezone.utc),
    )
    session.add(user)
    session.flush()
    return user


def _dataset(session, company: Company, name: str) -> Dataset:
    dataset = Dataset(
        id=uuid4(),
        company_id=company.id,
        name=name,
        type="csv",
        source=name,
        status=DatasetStatus.READY,
        rows_count=10,
        columns_count=3,
        uploaded_at=datetime.now(timezone.utc),
    )
    dataset.mapping = Mapping(mapping_json={"accepted": {}}, confidence=1, approved=True)
    session.add(dataset)
    session.flush()
    return dataset




def _document(db, company, user, number="INV-1"):
    document = TenantDocument(id=uuid4(), company_id=company.id, uploaded_by_user_id=user.id,
        kind="ocr", filename="invoice.txt", content_type="text/plain", byte_size=20,
        sha256="a" * 64, extracted_text=f"Invoice {number} Total 1379.70 CAD",
        classification="invoice", analysis_json=json.dumps({"fields": {"invoice_number": number, "total": "1379.70"}}))
    db.add(document)
    db.commit()
    return document

def test_ocr_proposals_keep_document_identity_and_require_review(db_session, monkeypatch):
    company = _company(db_session, "ocr-a")
    actor = _user(db_session, company)
    document = _document(db_session, company, actor)
    service = DocumentAIService(db_session)
    monkeypatch.setattr(service, "extract_structured_invoice", lambda _: SimpleNamespace(verification_status="verified", primary_invoice=None))
    first = service.propose_accounting_entry(actor, document.id)
    again = service.propose_accounting_entry(actor, document.id)
    assert first.id == again.id
    assert first.document_id == document.id
    assert first.source_module == "ocr"
    assert first.total_amount == 1379.70
    assert not first.is_confirmed
    assert first.verification_status == "to_verify"
    duplicate_doc = _document(db_session, company, actor)
    second = service.propose_accounting_entry(actor, duplicate_doc.id)
    assert second.id != first.id
    assert second.duplicate_warning
    other = _company(db_session, "ocr-b")
    other_actor = _user(db_session, other)
    with pytest.raises(LookupError):
        service.propose_accounting_entry(other_actor, document.id)

def test_ocr_inbox_is_tenant_scoped_and_separate_from_selected_dataset(db_session, monkeypatch):
    company = _company(db_session, "inbox-a")
    other = _company(db_session, "inbox-b")
    now = datetime.now(timezone.utc)
    for owner, number, source, doc_id in [
        (company, "OCR-A", "ocr", uuid4()), (other, "OCR-B", "ocr", uuid4()),
        (company, "MANUAL", "manual", None),
    ]:
        db_session.add(AccountingInvoice(company_id=owner.id, invoice_number=number,
            invoice_type="payable", party_name="Vendor", issue_date=now, due_date=now,
            total_amount=50, paid_amount=0, currency="CAD", status="unpaid",
            is_confirmed=False, source_module=source, document_id=doc_id))
    db_session.commit()
    monkeypatch.setattr(accounting, "resolve_accounting_dataset_scope", lambda *_: (frozenset(), {}))
    args = dict(invoice_type=None, status_filter=None, verification_status=None, document_nature=None,
        source_module=None, duplicate_warning=None, limit=200, tenant=TenantContext(company_id=company.id), db=db_session)
    assert accounting.list_invoices(document_scope=False, **args) == []
    rows = accounting.list_invoices(document_scope=True, **args)
    assert [row["invoice_number"] for row in rows] == ["OCR-A"]

def test_original_download_preserves_bytes_and_rejects_paths_outside_tenant(db_session, monkeypatch, tmp_path):
    from backend.app.routers import documents
    from fastapi import HTTPException
    company = _company(db_session, "original-a")
    actor = _user(db_session, company)
    document = _document(db_session, company, actor)
    original = b"%PDF-1.4 original logo bytes"
    relative = f"tenant_documents/{company.id}/ocr/invoice.pdf"
    target = tmp_path / relative
    target.parent.mkdir(parents=True)
    target.write_bytes(original)
    document.storage_path = relative
    document.filename = "invoice.pdf"
    db_session.commit()
    monkeypatch.setattr(documents, "_require_module", lambda *_: None)
    monkeypatch.setattr(documents, "get_settings", lambda: SimpleNamespace(artifact_root=tmp_path))
    kwargs = dict(document_id=document.id, identity=SimpleNamespace(user=actor), tenant=TenantContext(company_id=company.id),
                  db=db_session, service=DocumentAIService(db_session), _=None)
    response = documents.download_ocr_original(**kwargs)
    assert Path(response.path).read_bytes() == original
    document.storage_path = "../outside.pdf"
    db_session.commit()
    with pytest.raises(HTTPException) as error:
        documents.download_ocr_original(**kwargs)
    assert error.value.status_code == 404
