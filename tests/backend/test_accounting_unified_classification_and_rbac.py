"""Phase I2 — Suite complète de tests d'intégration, classification comptable, réconciliation, RBAC et isolation multi-tenant."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.testclient import TestClient
import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.ai.tools.business.accounting_tools import (
    AccountingGenericArgs,
    GetFinancialOverviewTool,
    GetInvoiceDetailArgs,
    GetInvoiceDetailTool,
    ReconcileSalesAndAccountingTool,
    SearchInvoicesArgs,
    SearchInvoicesTool,
)
from backend.app.ai.tools.contracts import ToolExecutionContext
from backend.app.core.permission_grants import encode_grants
from backend.app.database import get_db
from backend.app.dependencies.auth import CurrentIdentity, get_current_identity, get_tenant_context
from backend.app.models.accounting import (
    AccountingInvoice,
    AccountingTransaction,
)
from backend.app.models.audit_log import AuditLogEntry
from backend.app.models.base import Base, UserRole
from backend.app.models.billing import BillingAccount
from backend.app.models.commerce_connection import CommerceConnection, NormalizedCommerceRecord
from backend.app.models.company import Company
from backend.app.models.company_legal_profile import CompanyLegalProfile
from backend.app.models.company_membership import CompanyMembership
from backend.app.models.crm import CRMAppointment, CRMClient
from backend.app.models.user import User
from backend.app.models.workspace import TenantDocument
from backend.app.routers.accounting import router as accounting_router
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from backend.app.voice.caller_scope import PUBLIC_VOICE_CALLER_PERMISSIONS
from shared.ai_engine.contracts import TenantContext


@pytest.fixture
def accounting_env(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'accounting_unified_i2.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = session_factory()

    app = FastAPI()
    app.include_router(accounting_router, prefix="/api/v1")

    def _override_get_db():
        yield session

    def _override_current_identity(request: Request) -> CurrentIdentity:
        raw_uid = request.headers.get("X-Test-User-Id")
        if not raw_uid:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing test user header")
        user = session.get(User, UUID(raw_uid))
        if user is None or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid test user")
        return CurrentIdentity(auth_session=None, user=user, raw_token="test-token")

    def _override_tenant_context(
        identity: CurrentIdentity = pytest.importorskip("fastapi").Depends(_override_current_identity),
    ) -> TenantContext:
        return TenantContext(company_id=identity.company_id, user_id=identity.user_id)

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_identity] = _override_current_identity
    app.dependency_overrides[get_tenant_context] = _override_tenant_context

    client = TestClient(app)
    try:
        yield session, client, tmp_path
    finally:
        session.close()
        engine.dispose()


def _seed_tenant_with_users(
    session: Session,
    *,
    slug: str,
    legal_name: str,
    trade_name: str,
    gst_number: str,
    qst_number: str,
    domain: str,
    active_modules: tuple[str, ...] = ("accounting", "retail", "crm", "hr", "ocr"),
) -> dict[str, Any]:
    company = Company(
        id=uuid4(),
        name=trade_name,
        slug=slug,
        email=f"direction@{domain}",
        billing_email=f"facturation@{domain}",
        website=f"https://{domain}",
        country="CA",
        timezone="America/Montreal",
        industry="Retail & Services",
        currency_code="CAD",
        subscription_plan="enterprise",
    )
    session.add(company)
    session.flush()

    legal = CompanyLegalProfile(
        company_id=company.id,
        legal_name=legal_name,
        trade_name=trade_name,
        country="CA",
        province_state="QC",
        registration_number=f"NEQ-{slug[:6].upper()}1234",
        business_number=gst_number[:9],
        tax_id_gst=gst_number,
        tax_id_qst=qst_number,
        registered_address_street="1000 Rue Sherbrooke O",
        registered_address_city="Montréal",
        registered_address_state_province="QC",
        registered_address_postal_code="H3A 1G1",
        registered_address_country="CA",
        website=f"https://{domain}",
        phone="+15145550100",
        general_email=f"info@{domain}",
        billing_email=f"facturation@{domain}",
        industry="Retail & Services",
        authorized_representative_first_name="Claire",
        authorized_representative_last_name="Tremblay",
        authorized_representative_email=f"direction@{domain}",
        authorized_representative_title="Présidente",
        authorized_representative_authority_confirmed=True,
    )
    billing = BillingAccount(
        company_id=company.id,
        plan_code="enterprise",
        status="active",
    )
    session.add_all([legal, billing])
    session.flush()

    owner = User(
        id=uuid4(),
        company_id=company.id,
        first_name="Claire",
        last_name="Tremblay",
        job_title="Owner",
        department="Direction",
        email=f"owner@{domain}",
        password_hash="hashed",
        role=UserRole.OWNER,
        is_active=True,
    )
    billing_clerk = User(
        id=uuid4(),
        company_id=company.id,
        first_name="Marc",
        last_name="Gagnon",
        job_title="Préposé à la facturation",
        department="Comptabilité",
        email=f"clerk@{domain}",
        password_hash="hashed",
        role=UserRole.USER,
        permission_grants=encode_grants(("accounting:read", "tasks:own", "ai:use", "data:read")),
        is_active=True,
    )
    receptionist = User(
        id=uuid4(),
        company_id=company.id,
        first_name="Julie",
        last_name="Roy",
        job_title="Réceptionniste",
        department="Accueil",
        email=f"reception@{domain}",
        password_hash="hashed",
        role=UserRole.USER,
        permission_grants=encode_grants(("crm:appointments:read", "crm:appointments:write", "tasks:own")),
        is_active=True,
    )
    session.add_all([owner, billing_clerk, receptionist])
    session.flush()

    for usr, m_role in (
        (owner, UserRole.OWNER),
        (billing_clerk, UserRole.USER),
        (receptionist, UserRole.USER),
    ):
        session.add(
            CompanyMembership(
                company_id=company.id,
                user_id=usr.id,
                role=m_role,
                is_active=True,
            )
        )
    session.flush()

    ent_service = ModuleEntitlementService(session)
    t_ctx = TenantContext(company_id=company.id, user_id=owner.id)
    for mod_code in active_modules:
        ent_service.activate_module(t_ctx, mod_code)

    session.commit()
    return {
        "company": company,
        "legal": legal,
        "owner": owner,
        "billing_clerk": billing_clerk,
        "receptionist": receptionist,
    }


def _headers(user: User) -> dict[str, str]:
    return {"X-Test-User-Id": str(user.id)}


# 1) Supplier invoice (vendor=ABC, customer=Tenant) -> expense / payable (to_verify)
def test_1_supplier_invoice_classified_as_expense_payable_to_verify(accounting_env) -> None:
    session, client, _ = accounting_env
    tenant_a = _seed_tenant_with_users(
        session,
        slug="maison-nordique",
        legal_name="Maison Nordique Inc.",
        trade_name="Maison Nordique",
        gst_number="123456789RT0001",
        qst_number="1234567890TQ0001",
        domain="maisonnordique.ca",
    )
    owner = tenant_a["owner"]

    resp = client.post(
        "/api/v1/accounting/documents/classify",
        headers=_headers(owner),
        json={
            "invoice_number": "SUP-2026-8841",
            "issuer": "Fournitures ABC Ltée",
            "issuer_email": "factures@fournitures-abc.com",
            "recipient": "Maison Nordique Inc.",
            "recipient_tax_id": "123456789RT0001",
            "issue_date": "2026-10-15",
            "due_date": "2026-11-14",
            "subtotal_amount": "1000.00",
            "gst_amount": "50.00",
            "qst_amount": "99.75",
            "total_amount": "1149.75",
            "currency": "CAD",
            "line_items": [
                {"description": "Emballages biodégradables", "quantity": 10, "unit_price": "100.00", "total": "1000.00"}
            ],
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["classification"] == "supplier_invoice"
    assert body["invoice_type"] == "payable"
    assert body["direction"] == "expense"
    assert body["company_role"] == "customer_buyer"
    assert body["party_name"] == "Fournitures ABC Ltée"
    assert body["verification_status"] == "to_verify"
    assert body["accounting_status"] == "proposed"
    assert body["is_confirmed"] is False
    assert body["subtotal_amount"] == 1000.0
    assert body["tax_amount"] == 149.75
    assert body["total_amount"] == 1149.75
    assert body["math_validation"]["math_valid"] is True

    # Tant que la proposition n'est pas approuvée, les dépenses confirmées restent à 0.00
    overview = client.get("/api/v1/accounting/overview", headers=_headers(owner)).json()
    assert overview["total_expenses"] == 0.0
    assert overview["payables"]["unpaid_count"] == 0
    assert overview["pending_verification"]["to_verify_invoices_count"] == 1
    assert overview["pending_verification"]["proposed_payables_total"] == 1149.75


# 2) Issued client invoice (issuer=Tenant, customer=Client XYZ) -> revenue / receivable
def test_2_issued_client_invoice_classified_as_revenue_receivable(accounting_env) -> None:
    session, client, _ = accounting_env
    tenant_a = _seed_tenant_with_users(
        session,
        slug="atelier-boréal",
        legal_name="Atelier Boréal Inc.",
        trade_name="Atelier Boréal",
        gst_number="987654321RT0001",
        qst_number="9876543210TQ0001",
        domain="atelierboreal.ca",
    )
    owner = tenant_a["owner"]

    resp = client.post(
        "/api/v1/accounting/documents/classify",
        headers=_headers(owner),
        json={
            "invoice_number": "FAC-2026-0102",
            "issuer": "Atelier Boréal Inc.",
            "issuer_email": "facturation@atelierboreal.ca",
            "recipient": "Groupe Client XYZ Inc.",
            "issue_date": "2026-10-20",
            "due_date": "2026-11-19",
            "subtotal_amount": "2400.00",
            "gst_amount": "120.00",
            "qst_amount": "239.40",
            "total_amount": "2759.40",
            "currency": "CAD",
        },
    )
    assert resp.status_code == 201, resp.text
    proposal = resp.json()
    assert proposal["classification"] == "customer_invoice"
    assert proposal["invoice_type"] == "receivable"
    assert proposal["direction"] == "revenue"
    assert proposal["company_role"] == "issuer_supplier"
    assert proposal["party_name"] == "Groupe Client XYZ Inc."
    assert proposal["verification_status"] == "to_verify"
    assert proposal["is_confirmed"] is False

    # Approbation explicite par le propriétaire -> écriture confirmée au grand livre + créance AR active
    approve_resp = client.post(
        f"/api/v1/accounting/invoices/{proposal['invoice_id']}/review",
        headers=_headers(owner),
        json={"action": "approve", "reason": "Facture client émise et vérifiée"},
    )
    assert approve_resp.status_code == 200, approve_resp.text
    approved = approve_resp.json()
    assert approved["is_confirmed"] is True
    assert approved["verification_status"] == "approved"
    assert approved["accounting_status"] == "posted"

    overview = client.get("/api/v1/accounting/overview", headers=_headers(owner)).json()
    assert overview["total_revenue"] == 2400.0
    assert overview["taxes_summary"]["collected_sales_tax"] == 359.4
    assert overview["receivables"]["unpaid_count"] == 1
    assert overview["receivables"]["total_due"] == 2759.4


# 3) Credit note (avoir) & refund NEVER confused with a new sale
def test_3_credit_note_and_refund_never_confused_with_new_sale(accounting_env) -> None:
    session, client, _ = accounting_env
    tenant_a = _seed_tenant_with_users(
        session,
        slug="studio-verriere",
        legal_name="Studio Verrière Ltée",
        trade_name="Studio Verrière",
        gst_number="445566778RT0001",
        qst_number="4455667788TQ0001",
        domain="studioverriere.ca",
    )
    owner = tenant_a["owner"]

    # Enregistrer d'abord une vente confirmée de 1000.00 $ HT
    sale_prop = client.post(
        "/api/v1/accounting/documents/classify",
        headers=_headers(owner),
        json={
            "invoice_number": "FAC-100",
            "issuer": "Studio Verrière Ltée",
            "recipient": "Client Alpha Inc.",
            "subtotal_amount": "1000.00",
            "tax_amount": "149.75",
            "total_amount": "1149.75",
        },
    ).json()
    client.post(
        f"/api/v1/accounting/invoices/{sale_prop['invoice_id']}/review",
        headers=_headers(owner),
        json={"action": "approve", "reason": "Vente initiale confirmée"},
    )

    # Importer une note de crédit (avoir) émise par le tenant à Client Alpha
    cn_resp = client.post(
        "/api/v1/accounting/documents/classify",
        headers=_headers(owner),
        json={
            "invoice_number": "AVOIR-100-A",
            "document_type": "avoir",
            "issuer": "Studio Verrière Ltée",
            "recipient": "Client Alpha Inc.",
            "extracted_text": "NOTE DE CRÉDIT / AVOIR sur facture FAC-100",
            "subtotal_amount": "200.00",
            "tax_amount": "29.95",
            "total_amount": "229.95",
        },
    )
    assert cn_resp.status_code == 201
    cn = cn_resp.json()
    assert cn["classification"] == "credit_note"
    assert cn["invoice_type"] == "credit_note"
    assert cn["direction"] == "revenue_reversal"

    # Importer un remboursement client de 100.00 $ HT
    ref_resp = client.post(
        "/api/v1/accounting/documents/classify",
        headers=_headers(owner),
        json={
            "invoice_number": "REF-100-B",
            "document_type": "refund",
            "issuer": "Studio Verrière Ltée",
            "recipient": "Client Alpha Inc.",
            "extracted_text": "Avis de remboursement client",
            "subtotal_amount": "100.00",
            "tax_amount": "14.98",
            "total_amount": "114.98",
        },
    )
    assert ref_resp.status_code == 201
    ref = ref_resp.json()
    assert ref["classification"] == "refund"
    assert ref["invoice_type"] == "refund"
    assert ref["direction"] == "revenue_reversal"

    # Approuver l'avoir et le remboursement : le CA net DOIT diminuer (1000 - 200 - 100 = 700), JAMAIS augmenter à 1300 !
    client.post(
        f"/api/v1/accounting/invoices/{cn['invoice_id']}/review",
        headers=_headers(owner),
        json={"action": "approve", "reason": "Avoir client validé"},
    )
    client.post(
        f"/api/v1/accounting/invoices/{ref['invoice_id']}/review",
        headers=_headers(owner),
        json={"action": "approve", "reason": "Remboursement validé"},
    )

    overview = client.get("/api/v1/accounting/overview", headers=_headers(owner)).json()
    assert overview["gross_revenue"] == 1000.0
    assert overview["refunds_and_credit_notes_total"] == 300.0
    assert overview["total_revenue"] == 700.0


# 4) Duplicate invoice detection (file hash + business key match -> warning, no silent deletion)
def test_4_duplicate_detection_warns_without_deletion_and_requires_confirmation(accounting_env) -> None:
    session, client, _ = accounting_env
    tenant_a = _seed_tenant_with_users(
        session,
        slug="boulangerie-st-laurent",
        legal_name="Boulangerie St-Laurent Inc.",
        trade_name="Boulangerie St-Laurent",
        gst_number="555111222RT0001",
        qst_number="5551112220TQ0001",
        domain="boulangeriestlaurent.ca",
    )
    owner = tenant_a["owner"]
    pdf_hash = hashlib.sha256(b"%PDF-1.7-facture-meunerie-901").hexdigest()

    first = client.post(
        "/api/v1/accounting/documents/classify",
        headers=_headers(owner),
        json={
            "invoice_number": "MEU-2026-901",
            "issuer": "Meunerie Québec Inc.",
            "recipient": "Boulangerie St-Laurent Inc.",
            "issue_date": "2026-11-01",
            "subtotal_amount": "850.00",
            "tax_amount": "0.00",
            "total_amount": "850.00",
            "file_sha256": pdf_hash,
        },
    ).json()
    assert first["duplicate_warning"] is False

    # Réimport du même document (même hash + clés métier normalisées)
    second = client.post(
        "/api/v1/accounting/documents/classify",
        headers=_headers(owner),
        json={
            "invoice_number": "meu 2026 901",
            "issuer": "Meunerie Quebec",
            "recipient": "Boulangerie St-Laurent Inc.",
            "issue_date": "2026-11-01",
            "subtotal_amount": "850.00",
            "tax_amount": "0.00",
            "total_amount": "850.00",
            "file_sha256": pdf_hash,
        },
    ).json()
    assert second["duplicate_warning"] is True
    assert len(second["duplicate_candidates"]) == 1
    cand = second["duplicate_candidates"][0]
    assert cand["invoice_id"] == first["invoice_id"]
    assert "exact_file_sha256" in cand["match_reasons"]
    assert "exact_business_fingerprint" in cand["match_reasons"]

    # Aucune suppression silencieuse : les 2 propositions existent toujours en base
    all_invs = client.get("/api/v1/accounting/invoices", headers=_headers(owner)).json()
    assert len(all_invs) == 2

    # Approbation sans confirmation explicite -> bloquée en 409 Conflict
    blocked = client.post(
        f"/api/v1/accounting/invoices/{second['invoice_id']}/review",
        headers=_headers(owner),
        json={"action": "approve", "confirm_duplicate": False},
    )
    assert blocked.status_code == 409

    # Rejet propre du doublon -> tracé sans supprimer l'original
    rejected = client.post(
        f"/api/v1/accounting/invoices/{second['invoice_id']}/review",
        headers=_headers(owner),
        json={"action": "reject", "reason": "Doublon confirmé de MEU-2026-901"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["verification_status"] == "rejected"


# 5) Manual classification override + approval recorded in revision history & audit log
def test_5_manual_classification_override_and_approval_audit_trail(accounting_env) -> None:
    session, client, _ = accounting_env
    tenant_a = _seed_tenant_with_users(
        session,
        slug="clinique-horizon",
        legal_name="Clinique Horizon Inc.",
        trade_name="Clinique Horizon",
        gst_number="777888999RT0001",
        qst_number="7778889990TQ0001",
        domain="cliniquehorizon.ca",
    )
    owner = tenant_a["owner"]

    # Document ambigu sans nom d'entreprise reconnu -> basse confiance, `to_verify`
    prop = client.post(
        "/api/v1/accounting/documents/classify",
        headers=_headers(owner),
        json={
            "invoice_number": "AMB-2026-55",
            "issuer": "Entité Externe A",
            "recipient": "Service Gestion Externe",
            "subtotal_amount": "500.00",
            "tax_amount": "74.88",
            "total_amount": "574.88",
        },
    ).json()
    assert prop["company_role"] == "ambiguous"
    assert prop["verification_status"] == "to_verify"
    assert prop["confidence_score"] < 0.85

    # Le propriétaire corrige manuellement en `customer_invoice` (revenu) et approuve
    rev_resp = client.post(
        f"/api/v1/accounting/invoices/{prop['invoice_id']}/review",
        headers=_headers(owner),
        json={
            "action": "correct_and_approve",
            "classification": "customer_invoice",
            "category": "sales",
            "party_name": "Partenaire Médical Externe",
            "reason": "Sous-compte de facturation externe appartenant à notre clinique",
        },
    )
    assert rev_resp.status_code == 200, rev_resp.text
    reviewed = rev_resp.json()
    assert reviewed["classification"] == "customer_invoice"
    assert reviewed["invoice_type"] == "receivable"
    assert reviewed["direction"] == "revenue"
    assert reviewed["is_confirmed"] is True
    assert reviewed["revision_count"] == 2
    assert reviewed["latest_revision"]["revised_by"] == str(owner.id)
    assert reviewed["latest_revision"]["previous_values"]["document_nature"] == "supplier_invoice"
    assert reviewed["latest_revision"]["new_values"]["document_nature"] == "customer_invoice"
    assert reviewed["latest_revision"]["reason"] == "Sous-compte de facturation externe appartenant à notre clinique"

    # Vérifier la présence dans AuditLogEntry
    audits = list(
        session.scalars(
            select(AuditLogEntry).where(
                AuditLogEntry.company_id == tenant_a["company"].id,
                AuditLogEntry.target_id == prop["invoice_id"],
                AuditLogEntry.action == "accounting.invoice.correct_and_approve",
            )
        ).all()
    )
    assert len(audits) == 1
    assert audits[0].actor_user_id == owner.id
    assert audits[0].safe_metadata["new_classification"] == "customer_invoice"


# 6 & 7) Zero Shopify double-counting across repeated syncs + full reconciliation (order, payment, invoice, refund)
def test_6_and_7_shopify_idempotency_and_ecommerce_reconciliation(accounting_env) -> None:
    session, client, _ = accounting_env
    tenant_a = _seed_tenant_with_users(
        session,
        slug="velo-montreal",
        legal_name="Vélo Montréal Inc.",
        trade_name="Vélo Montréal",
        gst_number="333222111RT0001",
        qst_number="3332221110TQ0001",
        domain="velomontreal.ca",
    )
    company = tenant_a["company"]
    owner = tenant_a["owner"]

    conn = CommerceConnection(
        company_id=company.id,
        provider="shopify",
        external_account_id="velo-montreal.myshopify.com",
        status="READY",
        is_demo=False,
    )
    session.add(conn)
    session.flush()

    now = datetime.now(timezone.utc)
    # Produit avec coût unitaire vérifiable (40.00 $)
    prod_rec = NormalizedCommerceRecord(
        company_id=company.id,
        connection_id=conn.id,
        provider="shopify",
        entity_type="products",
        source_record_id="prod-casque-01",
        source_updated_at=now,
        normalized_data={"product_id": "prod-casque-01", "sku": "CSQ-PRO", "unit_cost": "40.00"},
        deleted=False,
        is_demo=False,
    )
    # Commande #1001 : 200.00 HT + 29.95 taxes = 229.95 TTC, frais Stripe/Shopify 6.90, remboursement partiel 50.00 HT + 7.49 taxes = 57.49 TTC
    order_rec = NormalizedCommerceRecord(
        company_id=company.id,
        connection_id=conn.id,
        provider="shopify",
        entity_type="orders",
        source_record_id="shp-order-1001",
        source_updated_at=now,
        normalized_data={
            "order_number": "1001",
            "financial_status": "partially_refunded",
            "subtotal_price": "200.00",
            "total_tax": "29.95",
            "total_price": "229.95",
            "processing_fee": "6.90",
            "currency": "CAD",
            "customer_name": "Émilie Bouchard",
            "payment_id": "pay-1001",
            "created_at": now.isoformat(),
            "line_items": [
                {"product_id": "prod-casque-01", "sku": "CSQ-PRO", "quantity": 2, "unit_price": "100.00", "total": "200.00"}
            ],
            "refunds": [
                {"id": "shp-ref-5001", "subtotal": "50.00", "tax_amount": "7.49", "amount": "57.49", "created_at": now.isoformat()}
            ],
        },
        deleted=False,
        is_demo=False,
    )
    session.add_all([prod_rec, order_rec])
    session.commit()

    # Avant sync : écart réel détecté honnêtement (aucune réconciliation fabriquée)
    pre_rec = client.get("/api/v1/accounting/reconciliation", headers=_headers(owner)).json()
    assert pre_rec["reconciled"] is False
    assert pre_rec["unlinked_orders_count"] == 1

    # Sync #1 avec approbation explicite des règlements connecteur vérifiés
    sync_1 = client.post(
        "/api/v1/accounting/integrations/retail/sync",
        headers=_headers(owner),
        json={"confirm_verified_settlements": True},
    ).json()
    assert sync_1["orders_processed"] == 1
    assert sync_1["refunds_synced"] == 1
    assert sync_1["created_invoices"] == 2  # Facture client + note de crédit remboursement
    assert sync_1["created_transactions"] == 6  # order, sale_revenue, payment_collected, cogs, processing_fee, refund

    # Sync #2 et Sync #3 répétés sur les mêmes enregistrements Shopify -> ZÉRO doublon !
    sync_2 = client.post(
        "/api/v1/accounting/integrations/retail/sync",
        headers=_headers(owner),
        json={"confirm_verified_settlements": True},
    ).json()
    sync_3 = client.post(
        "/api/v1/accounting/integrations/retail/sync",
        headers=_headers(owner),
        json={"confirm_verified_settlements": True},
    ).json()
    assert sync_2["created_invoices"] == 0
    assert sync_2["created_transactions"] == 0
    assert sync_2["skipped_idempotent"] > 0
    assert sync_3["created_transactions"] == 0

    # Vérifier la séparation stricte des écritures et l'absence de double comptage du CA
    overview = client.get("/api/v1/accounting/overview", headers=_headers(owner)).json()
    assert overview["gross_revenue"] == 200.0  # jamais doublé par `order` (229.95) ni par `payment_collected` (229.95)
    assert overview["refunds_and_credit_notes_total"] == 50.0
    assert overview["total_revenue"] == 150.0
    assert overview["cogs"] == 80.0  # 2 * 40.00 $ vérifié
    assert overview["processing_fees"] == 6.9
    assert overview["total_expenses"] == 86.9
    assert overview["payments_collected_total"] == 229.95

    # Réconciliation complète : 0.00 $ d'écart entre Retail AI et Accounting AI
    post_rec = client.get("/api/v1/accounting/reconciliation", headers=_headers(owner)).json()
    assert post_rec["reconciled"] is True
    assert post_rec["status"] == "reconciled"
    assert post_rec["discrepancy_amount"] == 0.0
    assert post_rec["net_discrepancy_amount"] == 0.0
    assert post_rec["matched_orders_count"] == 1
    assert len(post_rec["matched_orders"][0]["payment_transaction_ids"]) == 1
    assert post_rec["matched_orders"][0]["invoice_id"] is not None

    # Vérifier aussi l'outil IA ReconcileSalesAndAccountingTool
    tool_ctx = ToolExecutionContext(
        tenant=TenantContext(company_id=company.id, user_id=owner.id),
        user_id=owner.id,
        permissions=frozenset(["ai:use", "data:read"]),
        request_id="req-rec-1",
    )
    rec_tool_res = asyncio.run(ReconcileSalesAndAccountingTool(session).run(tool_ctx, AccountingGenericArgs()))
    assert rec_tool_res.success is True
    assert rec_tool_res.data["reconciled"] is True


# 8) Invoice detail endpoint & AI tool returning source document provenance, lines, math & linked entries
def test_8_invoice_detail_provenance_lines_math_and_linked_entries(accounting_env) -> None:
    session, client, _ = accounting_env
    tenant_a = _seed_tenant_with_users(
        session,
        slug="construction-nord",
        legal_name="Construction Nordique Inc.",
        trade_name="Construction Nordique",
        gst_number="666777888RT0001",
        qst_number="6667778880TQ0001",
        domain="constructionnordique.ca",
    )
    company = tenant_a["company"]
    owner = tenant_a["owner"]

    raw_bytes = "FACTURE FOURNISSEUR #MAT-7788\nDe: Matériaux Québec Inc.\nFacturé à: Construction Nordique Inc.\nTotal: 574.88".encode("utf-8")
    doc = TenantDocument(
        company_id=company.id,
        uploaded_by_user_id=owner.id,
        kind="ocr",
        filename="facture_materiaux_7788.pdf",
        content_type="application/pdf",
        byte_size=len(raw_bytes),
        sha256=hashlib.sha256(raw_bytes).hexdigest(),
        extracted_text=raw_bytes.decode("utf-8"),
        classification="invoice",
    )
    session.add(doc)
    session.commit()

    classified = client.post(
        "/api/v1/accounting/documents/classify",
        headers=_headers(owner),
        json={
            "document_id": str(doc.id),
            "invoice_number": "MAT-7788",
            "issuer": "Matériaux Québec Inc.",
            "recipient": "Construction Nordique Inc.",
            "subtotal_amount": "500.00",
            "gst_amount": "25.00",
            "qst_amount": "49.88",
            "total_amount": "574.88",
            "page_refs": [{"page": 1, "bbox": [12, 40, 520, 680]}],
            "line_items": [
                {"description": "Bois de charpente 2x6", "quantity": 50, "unit_price": "10.00", "total": "500.00", "source_ref": "p1:row1"}
            ],
        },
    ).json()

    inv_id = classified["invoice_id"]
    client.post(
        f"/api/v1/accounting/invoices/{inv_id}/review",
        headers=_headers(owner),
        json={"action": "approve", "reason": "Bon de livraison vérifié sur chantier"},
    )

    detail_resp = client.get(f"/api/v1/accounting/invoices/{inv_id}", headers=_headers(owner))
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["invoice_number"] == "MAT-7788"
    assert detail["provenance"]["document_id"] == str(doc.id)
    assert detail["provenance"]["source_document"]["filename"] == "facture_materiaux_7788.pdf"
    assert detail["provenance"]["source_document"]["sha256"] == doc.sha256
    assert detail["provenance"]["source_refs"]["page_refs"] == [{"page": 1, "bbox": [12, 40, 520, 680]}]
    assert len(detail["line_items"]) == 1
    assert detail["line_items"][0]["description"] == "Bois de charpente 2x6"
    assert detail["math_summary"]["subtotal_amount"] == 500.0
    assert detail["math_summary"]["tax_amount"] == 74.88
    assert detail["math_summary"]["total_amount"] == 574.88
    assert detail["math_summary"]["validation"]["math_valid"] is True
    assert len(detail["linked_entries"]) == 1
    assert detail["linked_entries"][0]["transaction_type"] == "expense"
    assert detail["linked_entries"][0]["amount"] == 500.0
    assert len(detail["revision_history"]) == 2
    assert len(detail["audit_trail"]) >= 2

    # Vérifier aussi via GetInvoiceDetailTool
    ctx = ToolExecutionContext(
        tenant=TenantContext(company_id=company.id, user_id=owner.id),
        user_id=owner.id,
        permissions=frozenset(["ai:use", "data:read"]),
        request_id="req-detail-1",
    )
    tool_res = asyncio.run(GetInvoiceDetailTool(session).run(ctx, GetInvoiceDetailArgs(invoice_id=inv_id)))
    assert tool_res.success is True
    assert tool_res.data["provenance"]["source_document"]["filename"] == "facture_materiaux_7788.pdf"


# 9) Owner full access vs restricted employee RBAC (including HR payroll isolation & public Voice caller refusal)
def test_9_owner_vs_restricted_employee_rbac_and_hr_payroll_isolation(accounting_env) -> None:
    session, client, _ = accounting_env
    tenant_a = _seed_tenant_with_users(
        session,
        slug="groupe-prestige",
        legal_name="Groupe Prestige Inc.",
        trade_name="Groupe Prestige",
        gst_number="101202303RT0001",
        qst_number="1012023030TQ0001",
        domain="groupeprestige.ca",
    )
    company = tenant_a["company"]
    owner = tenant_a["owner"]
    clerk = tenant_a["billing_clerk"]
    receptionist = tenant_a["receptionist"]

    # Ajouter une écriture confirmée de masse salariale globale
    session.add(
        AccountingTransaction(
            company_id=company.id,
            transaction_date=datetime.now(timezone.utc),
            transaction_type="expense",
            entry_kind="payroll_summary",
            category="payroll",
            description="Paie bimensuelle équipe",
            amount=18500.0,
            currency="CAD",
            status="confirmed",
            is_confirmed=True,
            source_module="hr",
            extra_data={"department": "Opérations"},
        )
    )
    # Ajouter un rendez-vous CRM complété facturable
    crm_client = CRMClient(
        company_id=company.id,
        first_name="Sophie",
        last_name="Martin",
        email="sophie@client.ca",
    )
    session.add(crm_client)
    session.flush()
    session.add(
        CRMAppointment(
            company_id=company.id,
            client_id=crm_client.id,
            title="Consultation Stratégique",
            start_time=datetime.now(timezone.utc) - timedelta(hours=2),
            end_time=datetime.now(timezone.utc) - timedelta(hours=1),
            status="completed",
            price=450.0,
            currency="CAD",
        )
    )
    session.commit()

    # 1. Propriétaire (Owner) : accès complet écriture + CRM sync + masse salariale agrégée (sans dossiers personnels)
    crm_sync = client.post("/api/v1/accounting/integrations/crm/sync", headers=_headers(owner))
    assert crm_sync.status_code == 200
    assert crm_sync.json()["created_proposals"] == 1

    owner_payroll = client.get("/api/v1/accounting/payroll-summary", headers=_headers(owner))
    assert owner_payroll.status_code == 200
    p_data = owner_payroll.json()
    assert p_data["access_granted"] is True
    assert p_data["personal_records_exposed"] is False
    assert p_data["total_confirmed_payroll_cost"] == 18500.0

    owner_unified = client.get("/api/v1/accounting/overview/unified", headers=_headers(owner)).json()
    assert owner_unified["unified_sources"]["hr_payroll"]["access_granted"] is True

    # 2. Préposé à la facturation (accounting:read uniquement, pas accounting:write, pas exécutif RH)
    clerk_overview = client.get("/api/v1/accounting/overview", headers=_headers(clerk))
    assert clerk_overview.status_code == 200

    clerk_write = client.post(
        "/api/v1/accounting/documents/classify",
        headers=_headers(clerk),
        json={"issuer": "Test", "recipient": "Groupe Prestige Inc.", "total_amount": "100.00"},
    )
    assert clerk_write.status_code == 403

    clerk_payroll = client.get("/api/v1/accounting/payroll-summary", headers=_headers(clerk))
    assert clerk_payroll.status_code == 403

    clerk_unified = client.get("/api/v1/accounting/overview/unified", headers=_headers(clerk)).json()
    assert clerk_unified["unified_sources"]["hr_payroll"]["access_granted"] is False
    assert "total_confirmed_payroll_cost" not in clerk_unified["unified_sources"]["hr_payroll"]

    # 3. Réceptionniste (aucun droit comptable) -> 403 sur lecture et écriture
    rec_overview = client.get("/api/v1/accounting/overview", headers=_headers(receptionist))
    assert rec_overview.status_code == 403

    # 4. Appelant vocal public non authentifié -> refus strict sur les outils Accounting AI
    public_voice_ctx = ToolExecutionContext(
        tenant=TenantContext(company_id=company.id),
        user_id=owner.id,
        permissions=PUBLIC_VOICE_CALLER_PERMISSIONS,
        request_id="voice-pub-1",
        voice_path=True,
    )
    pub_res = asyncio.run(GetFinancialOverviewTool(session).run(public_voice_ctx, AccountingGenericArgs()))
    assert pub_res.success is False
    assert "confidentielles" in (pub_res.error or "")


# 10) Strict multi-tenant isolation (Company A cannot read, classify, reconcile, or approve Company B's data)
def test_10_strict_multi_tenant_isolation_zero_leak(accounting_env) -> None:
    session, client, _ = accounting_env
    tenant_a = _seed_tenant_with_users(
        session,
        slug="compagnie-alpha",
        legal_name="Compagnie Alpha Inc.",
        trade_name="Compagnie Alpha",
        gst_number="111000111RT0001",
        qst_number="1110001110TQ0001",
        domain="compagniealpha.ca",
    )
    tenant_b = _seed_tenant_with_users(
        session,
        slug="compagnie-beta",
        legal_name="Compagnie Beta Inc.",
        trade_name="Compagnie Beta",
        gst_number="222000222RT0001",
        qst_number="2220002220TQ0001",
        domain="compagniebeta.ca",
    )
    owner_a = tenant_a["owner"]
    owner_b = tenant_b["owner"]

    # Créer un document OCR et une facture dans Company B
    doc_b = TenantDocument(
        company_id=tenant_b["company"].id,
        uploaded_by_user_id=owner_b.id,
        kind="ocr",
        filename="secret_beta.pdf",
        content_type="application/pdf",
        byte_size=64,
        sha256=hashlib.sha256(b"beta-secret-invoice").hexdigest(),
        extracted_text="Total: 9999.00",
    )
    session.add(doc_b)
    session.commit()

    inv_b = client.post(
        "/api/v1/accounting/documents/classify",
        headers=_headers(owner_b),
        json={
            "document_id": str(doc_b.id),
            "invoice_number": "BETA-SECRET-001",
            "issuer": "Fournisseur Beta",
            "recipient": "Compagnie Beta Inc.",
            "total_amount": "9999.00",
        },
    ).json()
    inv_b_id = inv_b["invoice_id"]

    # Company A tente de lire le détail de la facture de Company B -> 404 (zéro fuite)
    read_cross = client.get(f"/api/v1/accounting/invoices/{inv_b_id}", headers=_headers(owner_a))
    assert read_cross.status_code == 404

    # Company A tente d'approuver ou rejeter la facture de Company B -> 404
    approve_cross = client.post(
        f"/api/v1/accounting/invoices/{inv_b_id}/review",
        headers=_headers(owner_a),
        json={"action": "approve"},
    )
    assert approve_cross.status_code == 404

    # Company A tente de classifier le TenantDocument de Company B -> 404
    classify_cross_doc = client.post(
        "/api/v1/accounting/documents/classify",
        headers=_headers(owner_a),
        json={"document_id": str(doc_b.id), "total_amount": "9999.00"},
    )
    assert classify_cross_doc.status_code == 404

    # Company A liste ses factures et cherche "BETA-SECRET" via outil IA -> 0 résultat
    list_a = client.get("/api/v1/accounting/invoices", headers=_headers(owner_a)).json()
    assert list_a == []

    ctx_a = ToolExecutionContext(
        tenant=TenantContext(company_id=tenant_a["company"].id, user_id=owner_a.id),
        user_id=owner_a.id,
        permissions=frozenset(["ai:use", "data:read"]),
        request_id="iso-search-a",
    )
    search_res = asyncio.run(SearchInvoicesTool(session).run(ctx_a, SearchInvoicesArgs(query="BETA-SECRET")))
    assert search_res.success is True
    assert search_res.data["count"] == 0

    detail_res = asyncio.run(GetInvoiceDetailTool(session).run(ctx_a, GetInvoiceDetailArgs(invoice_id=inv_b_id)))
    assert detail_res.success is False


# 11) Alembic migration 0089 idempotency on legacy SQLite schema
def test_11_alembic_migration_0089_is_idempotent_and_sqlite_compatible(tmp_path: Path) -> None:
    mig_path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "0089_accounting_unified_ledger_and_proposals.py"
    )
    spec = importlib.util.spec_from_file_location("mig_0089", mig_path)
    assert spec is not None and spec.loader is not None
    mig_0089 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig_0089)
    assert mig_0089.down_revision == "0088_hr_skills_and_evidence"

    legacy_engine = create_engine(f"sqlite:///{tmp_path / 'legacy_0088.db'}")
    with legacy_engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE companies (id VARCHAR(36) PRIMARY KEY)"))
        conn.execute(
            sa.text(
                "CREATE TABLE accounting_transactions ("
                "id VARCHAR(36) PRIMARY KEY, company_id VARCHAR(36) NOT NULL, "
                "transaction_date TIMESTAMP NOT NULL, transaction_type VARCHAR(50) NOT NULL, "
                "category VARCHAR(100) NOT NULL, description VARCHAR(255) NOT NULL, "
                "amount FLOAT NOT NULL, currency VARCHAR(10) NOT NULL, "
                "status VARCHAR(50) NOT NULL, is_confirmed BOOLEAN NOT NULL, "
                "tax_amount FLOAT NOT NULL, reference_id VARCHAR(100), extra_data JSON NOT NULL)"
            )
        )
        conn.execute(
            sa.text(
                "CREATE TABLE accounting_invoices ("
                "id VARCHAR(36) PRIMARY KEY, company_id VARCHAR(36) NOT NULL, "
                "invoice_number VARCHAR(100) NOT NULL, invoice_type VARCHAR(50) NOT NULL, "
                "party_name VARCHAR(255) NOT NULL, issue_date TIMESTAMP NOT NULL, "
                "due_date TIMESTAMP NOT NULL, total_amount FLOAT NOT NULL, "
                "paid_amount FLOAT NOT NULL, currency VARCHAR(10) NOT NULL, "
                "status VARCHAR(50) NOT NULL, is_confirmed BOOLEAN NOT NULL, notes TEXT)"
            )
        )

        conn.execute(
            sa.text(
                "INSERT INTO companies (id) VALUES ('c1')"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO accounting_invoices (id, company_id, invoice_number, invoice_type, party_name, "
                "issue_date, due_date, total_amount, paid_amount, currency, status, is_confirmed) "
                "VALUES ('inv-unconf', 'c1', 'OCR-1', 'payable', 'Vendor', '2026-11-01', '2026-12-01', 150.0, 0.0, 'CAD', 'unpaid', 0), "
                "('inv-conf', 'c1', 'MAN-1', 'receivable', 'Client', '2026-11-01', '2026-12-01', 300.0, 300.0, 'CAD', 'paid', 1)"
            )
        )

        mc = MigrationContext.configure(conn)
        with Operations.context(mc):
            # Exécution #1 et #2 consécutives pour prouver l'idempotence stricte
            mig_0089.upgrade()
            mig_0089.upgrade()

        rows = conn.execute(
            sa.text("SELECT id, verification_status, accounting_status FROM accounting_invoices ORDER BY id")
        ).fetchall()
        assert dict((r[0], (r[1], r[2])) for r in rows) == {
            "inv-conf": ("confirmed", "posted"),
            "inv-unconf": ("to_verify", "proposed"),
        }

        insp = sa.inspect(conn)
        tables = set(insp.get_table_names())
        assert "accounting_tenant_policies" in tables
        assert "accounting_classification_rules" in tables
        inv_cols = {c["name"] for c in insp.get_columns("accounting_invoices")}
        assert {"document_nature", "company_role", "verification_status", "duplicate_fingerprint", "revision_history"}.issubset(inv_cols)
        tx_cols = {c["name"] for c in insp.get_columns("accounting_transactions")}
        assert {"entry_kind", "idempotency_key", "invoice_id", "verification_status", "accounting_status"}.issubset(tx_cols)
    legacy_engine.dispose()


def test_12_audit_pr135_all_23_copilot_threads_and_universal_accounting(accounting_env) -> None:
    """Verifies all 23 Copilot review threads on PR #135 and universal cross-module accounting requirements."""
    session, client, _ = accounting_env
    tenant = _seed_tenant_with_users(
        session,
        slug="industrie-nord",
        legal_name="Industrie Nord Inc.",
        trade_name="Industrie Nord",
        gst_number="444555666RT0001",
        qst_number="4445556660TQ0001",
        domain="industrienord.ca",
        active_modules=("accounting", "retail", "crm", "ocr", "hr", "voice"),
    )
    company = tenant["company"]
    owner = tenant["owner"]
    clerk = tenant["billing_clerk"]

    # Thread 2: Clerk with accounting:read cannot bypass payroll restriction via /transactions?category=payroll or /expenses/monthly
    session.add(
        AccountingTransaction(
            company_id=company.id,
            transaction_date=datetime.now(timezone.utc),
            transaction_type="expense",
            entry_kind="payroll_summary",
            category="payroll",
            description="Paie confidentielle direction",
            amount=25000.0,
            currency="CAD",
            status="confirmed",
            is_confirmed=True,
            source_module="hr",
        )
    )
    session.commit()
    clerk_payroll_tx = client.get("/api/v1/accounting/transactions?category=payroll", headers=_headers(clerk))
    assert clerk_payroll_tx.status_code == 403
    clerk_all_tx = client.get("/api/v1/accounting/transactions", headers=_headers(clerk)).json()
    assert all(t["category"] != "payroll" for t in clerk_all_tx)
    clerk_monthly = client.get("/api/v1/accounting/expenses/monthly", headers=_headers(clerk)).json()
    assert all(c["category"] != "payroll" for c in clerk_monthly["categories_breakdown"])

    # Threads 3 & 4: Configured QST rate 0.09975 is NOT rounded to 0.10, and breakdown_sum is refreshed so math_valid=True
    client.put(
        "/api/v1/accounting/policy",
        headers=_headers(owner),
        json={"configured_tax_rules": {"gst_tps": "0.05", "qst_tvq": "0.09975"}},
    )
    qst_prop = client.post(
        "/api/v1/accounting/documents/classify",
        headers=_headers(owner),
        json={
            "invoice_number": "QST-1000",
            "issuer": "Industrie Nord Inc.",
            "recipient": "Client Québec Inc.",
            "subtotal_amount": "1000.00",
            "apply_configured_tax_rules": True,
        },
    ).json()
    assert qst_prop["tax_amount"] == 149.75
    assert qst_prop["total_amount"] == 1149.75
    assert qst_prop["math_validation"]["math_valid"] is True

    # Thread 5: Explicit transfer signal with tenant on one side stays neutral transfer (to_verify)
    tr_prop = client.post(
        "/api/v1/accounting/documents/classify",
        headers=_headers(owner),
        json={
            "invoice_number": "VIR-001",
            "document_type": "transfer",
            "issuer": "Industrie Nord Inc.",
            "recipient": "Banque Nationale Compte Épargne",
            "total_amount": "5000.00",
        },
    ).json()
    assert tr_prop["classification"] == "transfer"
    assert tr_prop["direction"] == "neutral"
    assert tr_prop["verification_status"] == "to_verify"

    # Threads 6, 7, 9, 11: Post-correction duplicate check, amount revalidation, and unconfirming on 'correct'
    p1 = client.post(
        "/api/v1/accounting/documents/classify",
        headers=_headers(owner),
        json={
            "invoice_number": "DUP-EDIT-1",
            "issuer": "Fournisseur Unique",
            "recipient": "Industrie Nord Inc.",
            "issue_date": "2026-11-15",
            "subtotal_amount": "500.00",
            "tax_amount": "0.00",
            "total_amount": "500.00",
        },
    ).json()
    p2 = client.post(
        "/api/v1/accounting/documents/classify",
        headers=_headers(owner),
        json={
            "invoice_number": "DUP-EDIT-1",
            "issuer": "Autre Fournisseur Initial",
            "recipient": "Industrie Nord Inc.",
            "issue_date": "2026-11-15",
            "subtotal_amount": "300.00",
            "tax_amount": "0.00",
            "total_amount": "300.00",
        },
    ).json()
    # Correcting p2 to match p1's party and total must trigger DuplicateConfirmationRequiredError (409) without confirm_duplicate!
    dup_conflict = client.post(
        f"/api/v1/accounting/invoices/{p2['invoice_id']}/review",
        headers=_headers(owner),
        json={
            "action": "correct_and_approve",
            "party_name": "Fournisseur Unique",
            "total_amount": "500.00",
        },
    )
    assert dup_conflict.status_code == 409

    # Approving p1 with only total_amount=1000 updates subtotal_amount to 1000 and posts 1000 to ledger
    app_p1 = client.post(
        f"/api/v1/accounting/invoices/{p1['invoice_id']}/review",
        headers=_headers(owner),
        json={"action": "correct_and_approve", "total_amount": "1000.00", "confirm_duplicate": True},
    ).json()
    assert app_p1["subtotal_amount"] == 1000.0
    assert app_p1["total_amount"] == 1000.0
    # Calling 'correct' on an approved invoice unconfirms its linked ledger transaction
    unconf_p1 = client.post(
        f"/api/v1/accounting/invoices/{p1['invoice_id']}/review",
        headers=_headers(owner),
        json={"action": "correct", "reason": "Retour en brouillon pour vérification"},
    ).json()
    assert unconf_p1["is_confirmed"] is False
    tx_p1 = session.get(AccountingTransaction, UUID(app_p1["linked_transaction_id"]))
    assert tx_p1 is not None and tx_p1.is_confirmed is False

    # Threads 15, 16, 17, 18, 19, 20, 21, 22, 23: Multi-store connection_id namespace, order_timestamp, unverified settlement not paid, refund_amount & retry state promotion
    store_1 = CommerceConnection(
        company_id=company.id,
        provider="woocommerce",
        external_account_id="store-1.example.com",
        status="READY",
        is_demo=False,
    )
    store_2 = CommerceConnection(
        company_id=company.id,
        provider="woocommerce",
        external_account_id="store-2.example.com",
        status="READY",
        is_demo=False,
    )
    session.add_all([store_1, store_2])
    session.flush()

    hist_ts = "2026-09-10T14:30:00+00:00"
    now_ts = datetime.now(timezone.utc)
    # Both stores have order "1001"! Store 1 has no financial_status (must NOT default to paid!); Store 2 is paid with refund_amount
    ord_s1 = NormalizedCommerceRecord(
        company_id=company.id,
        connection_id=store_1.id,
        provider="woocommerce",
        entity_type="orders",
        source_record_id="1001",
        source_updated_at=now_ts,
        normalized_data={
            "order_number": "1001",
            "order_timestamp": hist_ts,
            "subtotal_price": "100.00",
            "total_tax": "15.00",
            "total_price": "115.00",
            "currency": "CAD",
        },
        deleted=False,
        is_demo=False,
    )
    ord_s2 = NormalizedCommerceRecord(
        company_id=company.id,
        connection_id=store_2.id,
        provider="woocommerce",
        entity_type="orders",
        source_record_id="1001",
        source_updated_at=now_ts,
        normalized_data={
            "order_number": "1001",
            "order_timestamp": hist_ts,
            "financial_status": "paid",
            "subtotal_price": "200.00",
            "total_tax": "30.00",
            "total_price": "230.00",
            "currency": "CAD",
            "refunds": [
                {"id": "ref-s2-1", "refund_amount": "57.50", "tax_amount": "7.50", "refund_timestamp": hist_ts}
            ],
        },
        deleted=False,
        is_demo=False,
    )
    # Duplicate standalone representation of the same refund ref-s2-1 -> must be deduplicated in reconciliation
    standalone_ref_s2 = NormalizedCommerceRecord(
        company_id=company.id,
        connection_id=store_2.id,
        provider="woocommerce",
        entity_type="refunds",
        source_record_id="ref-s2-1",
        source_updated_at=now_ts,
        normalized_data={
            "source_order_id": "1001",
            "refund_amount": "57.50",
            "tax_amount": "7.50",
            "refund_timestamp": hist_ts,
        },
        deleted=False,
        is_demo=False,
    )
    session.add_all([ord_s1, ord_s2, standalone_ref_s2])
    session.commit()

    # First sync with confirm_verified_settlements=False -> all proposals
    s_first = client.post(
        "/api/v1/accounting/integrations/retail/sync",
        headers=_headers(owner),
        json={"confirm_verified_settlements": False},
    ).json()
    assert s_first["orders_processed"] == 2
    assert s_first["created_invoices"] == 3  # Store 1 order 1001 + Store 2 order 1001 + Store 2 credit note

    # Retry with confirm_verified_settlements=True -> promotes Store 2 (paid), keeps Store 1 (unverified) as to_verify!
    s_retry = client.post(
        "/api/v1/accounting/integrations/retail/sync",
        headers=_headers(owner),
        json={"confirm_verified_settlements": True},
    ).json()
    assert s_retry["created_invoices"] == 0

    invs_all = client.get("/api/v1/accounting/invoices?source_module=retail", headers=_headers(owner)).json()
    s1_inv = next(i for i in invs_all if i["total_amount"] == 115.0)
    s2_inv = next(i for i in invs_all if i["total_amount"] == 230.0)
    assert s1_inv["is_confirmed"] is False
    assert s1_inv["verification_status"] == "to_verify"
    assert s1_inv["paid_amount"] == 0.0
    assert s1_inv["issue_date"].startswith("2026-09-10")
    assert s2_inv["is_confirmed"] is True
    assert s2_inv["paid_amount"] == 230.0
    assert s2_inv["issue_date"].startswith("2026-09-10")

    from backend.app.services.retail_source_service import RetailSourceService
    from shared.ai_engine.contracts import TenantContext

    source_service = RetailSourceService(session)
    accounting_user = TenantContext(company.id, user_id=owner.id)
    for store, expected in ((store_1, 115.0), (store_2, 230.0), (store_1, 115.0)):
        source_service.select_source(accounting_user, source_type="connector", source_id=store.id)
        selected_invoices = client.get(
            "/api/v1/accounting/invoices?source_module=retail", headers=_headers(owner)
        ).json()
        assert expected in {invoice["total_amount"] for invoice in selected_invoices}
        other = 230.0 if expected == 115.0 else 115.0
        assert other not in {invoice["total_amount"] for invoice in selected_invoices}
    source_service.select_source(accounting_user, source_type="all")

    # Thread 13: Cash flow forecast excludes unpaid accrual invoices from current_balance
    cf = client.get("/api/v1/accounting/forecast/cashflow", headers=_headers(owner)).json()
    assert cf["is_projection"] is True

