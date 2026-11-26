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
from tests.backend.test_accounting_active_source import db_session, _company, _user

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
