"""Couche d'intégration financière unifiée pour Accounting AI (Phase D).

Connecte de manière sécurisée, multi-tenant et sans double comptabilisation les données financières de :
- Retail AI : commandes, ventes complétées, remboursements/retours, taxes de vente documentées,
  COGS vérifiables, frais de traitement et marges vérifiables avec `idempotency_key` déterministe.
  Sépare explicitement `order`, `payment_collected`, `invoice`, `refund` et `journal_entry`.
- CRM AI : clients actifs, rendez-vous facturables complétés, contrats et soldes clients.
- OCR AI / Documents & Datasets : factures et pièces justificatives avec traçabilité complète.
- HR AI : masse salariale agrégée UNIQUEMENT si le module HR est actif ET l'appelant détient
  les droits exécutifs/paie — aucune fiche individuelle RH n'est jamais exposée.
- Voice AI : lecture financière filtrée par RBAC staff vérifié (aucune divulgation publique).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.permission_grants import effective_permissions
from backend.app.core.permissions import is_executive_role, resolve_verified_staff_role
from ..models.accounting import (
    AccountingInvoice,
    AccountingTenantPolicy,
    AccountingTransaction,
)
from backend.app.models.audit_log import AuditLogEntry
from backend.app.models.commerce_connection import NormalizedCommerceRecord
from backend.app.models.company_contract import CompanyContract
from backend.app.models.crm import CRMAppointment, CRMClient
from backend.app.models.user import User
from backend.app.models.workspace import TenantDocument
from .accounting_classification_service import (
     TWOPLACES,
    _parse_datetime,
    _to_decimal,
)
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from shared.ai_engine.contracts import TenantContext


class HRPayrollAccessDeniedError(PermissionError):
    """Accès refusé aux données agrégées de masse salariale RH."""


PAYROLL_CATEGORIES: frozenset[str] = frozenset({
    "payroll",
    "salaries",
    "salaires",
    "employer_taxes",
    "paie",
    "masse_salariale",
})


def _extract_canonical_refund_fields(
    refund_data: dict[str, Any],
    *,
    default_date: Any = None,
) -> tuple[Decimal, Decimal, Decimal, datetime, str]:
    """Extrait les montants et identifiants canoniques d'un remboursement (supporte `refund_amount`, `amount`, `total_refund`, `source_order_id`, `shopify_order_gid`, `refund_timestamp`)."""
    raw_gross = (
        refund_data.get("amount")
        if refund_data.get("amount") is not None
        else (
            refund_data.get("refund_amount")
            if refund_data.get("refund_amount") is not None
            else (
                refund_data.get("total_refund")
                if refund_data.get("total_refund") is not None
                else refund_data.get("total_amount")
            )
        )
    )
    ref_gross = _to_decimal(raw_gross, default=Decimal("0.00")) or Decimal("0.00")
    ref_tax = (
        _to_decimal(
            refund_data.get("tax_amount")
            if refund_data.get("tax_amount") is not None
            else refund_data.get("total_tax"),
            default=Decimal("0.00"),
        )
        or Decimal("0.00")
    )
    ref_sub = _to_decimal(refund_data.get("subtotal"), default=None)
    if ref_sub is None:
        ref_sub = max(Decimal("0.00"), (ref_gross - ref_tax).quantize(TWOPLACES, rounding=ROUND_HALF_UP))
    ref_date = _parse_datetime(
        refund_data.get("refund_timestamp")
        or refund_data.get("created_at")
        or refund_data.get("processed_at")
        or default_date
    )
    raw_ord = (
        refund_data.get("order_id")
        or refund_data.get("source_order_id")
        or refund_data.get("shopify_order_gid")
        or refund_data.get("order_external_id")
        or ""
    )
    order_ext_id = str(raw_ord).strip()
    if "/" in order_ext_id and order_ext_id.startswith("gid://"):
        order_ext_id = order_ext_id.rsplit("/", 1)[-1]
    return ref_gross, ref_tax, ref_sub, ref_date, order_ext_id


def can_access_hr_payroll_summary(
    session: Session,
    company_id: UUID,
    actor_user: User | None,
) -> tuple[bool, str]:
    """Vérifie la double condition stricte : module HR actif + droits exécutifs/paie explicites."""
    if actor_user is None:
        return False, "unauthenticated_actor"
    if actor_user.company_id != company_id or not getattr(actor_user, "is_active", True):
        return False, "cross_tenant_or_inactive_actor"
    if getattr(actor_user, "is_platform_admin", False):
        return False, "platform_admin_no_private_hr_access"

    tenant = TenantContext(company_id=company_id, user_id=actor_user.id)
    if not ModuleEntitlementService(session).can_use_module(tenant, "hr"):
        return False, "hr_module_inactive"

    verified_role = resolve_verified_staff_role(
        session,
        company_id,
        actor_user.id,
        fallback_role=getattr(actor_user, "role", None),
    )
    held_perms = set(effective_permissions(actor_user))

    # Seuls Owner/Admin (exécutif direction) ou permission explicite `hr:payroll:read` / `company:manage`
    if verified_role in {"owner", "admin"} or "hr:payroll:read" in held_perms or "company:manage" in held_perms:
        return True, "authorized"

    return False, "insufficient_hr_payroll_permissions"


class FinancialIntegrationService:
    """Orchestre la synchronisation idempotente et la réconciliation inter-modules."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def _get_policy(self, company_id: UUID) -> AccountingTenantPolicy | None:
        return self._session.scalar(
            select(AccountingTenantPolicy).where(AccountingTenantPolicy.company_id == company_id)
        )

    def _lookup_product_costs(self, company_id: UUID) -> dict[str, Decimal]:
        """Récupère les coûts unitaires vérifiables des produits Retail AI (jamais inventés)."""
        products = list(
            self._session.scalars(
                select(NormalizedCommerceRecord).where(
                    NormalizedCommerceRecord.company_id == company_id,
                    NormalizedCommerceRecord.entity_type == "products",
                    NormalizedCommerceRecord.deleted.is_(False),
                )
            ).all()
        )
        costs: dict[str, Decimal] = {}
        for prod in products:
            pdata = prod.normalized_data or {}
            raw_cost = pdata.get("unit_cost") or pdata.get("cost") or pdata.get("cost_per_item")
            dec_cost = _to_decimal(raw_cost, default=None)
            if dec_cost is not None and dec_cost >= Decimal("0.00"):
                ext_pid = str(prod.source_record_id)
                conn_id_val = getattr(prod, "connection_id", None)
                costs[ext_pid] = dec_cost
                if conn_id_val:
                    costs[f"{conn_id_val}:{ext_pid}"] = dec_cost
                if pdata.get("sku"):
                    costs[f"sku:{pdata['sku']}"] = dec_cost
                    if conn_id_val:
                        costs[f"{conn_id_val}:sku:{pdata['sku']}"] = dec_cost
        return costs

    @staticmethod
    def _connection_namespace(provider: str, record: Any) -> str:
        conn_id = getattr(record, "connection_id", None)
        if conn_id is not None and str(conn_id).strip():
            return f"{provider}:{str(conn_id).strip()}"
        return provider

    def sync_retail_commerce_to_accounting(
        self,
        company_id: UUID,
        *,
        actor_user_id: UUID | None = None,
        confirm_verified_settlements: bool | None = None,
        include_demo: bool = False,
    ) -> dict[str, Any]:
        """Synchronise commandes, ventes, paiements, taxes, COGS connus, frais et remboursements Retail AI.

        Utilise des `idempotency_key` déterministes incluant la connexion (`{provider}[:{connection_id}]:{company_id}:{ext_id}:{event_type}`)
        garantissant ZÉRO double comptage et ZÉRO collision multi-boutiques.
        """
        tenant = TenantContext(company_id=company_id, user_id=actor_user_id)
        if not ModuleEntitlementService(self._session).can_use_module(tenant, "retail"):
            return {
                "available": False,
                "source_module": "retail",
                "reason": "retail_module_inactive",
                "orders_processed": 0,
                "refunds_synced": 0,
                "created_invoices": 0,
                "created_transactions": 0,
                "skipped_idempotent": 0,
                "governance_mode": "module_inactive",
            }

        policy = self._get_policy(company_id)
        auto_confirm = (
            bool(confirm_verified_settlements)
            if confirm_verified_settlements is not None
            else bool(policy.auto_confirm_verified_connector_settlements if policy else False)
        )

        stmt = select(NormalizedCommerceRecord).where(
            NormalizedCommerceRecord.company_id == company_id,
            NormalizedCommerceRecord.deleted.is_(False),
        )
        if not include_demo:
            stmt = stmt.where(NormalizedCommerceRecord.is_demo.is_(False))

        records = list(self._session.scalars(stmt).all())
        order_records = [r for r in records if r.entity_type == "orders"]
        standalone_refunds = [r for r in records if r.entity_type == "refunds"]
        product_costs = self._lookup_product_costs(company_id)

        created_invoices = 0
        created_transactions = 0
        skipped_idempotent = 0
        orders_synced = 0
        refunds_synced = 0

        invoice_by_order_ext: dict[str, AccountingInvoice] = {}
        processed_refund_identities: set[str] = set()

        for ord_rec in order_records:
            data = ord_rec.normalized_data or {}
            provider = (ord_rec.provider or "shopify").lower().strip()
            conn_ns = self._connection_namespace(provider, ord_rec)
            conn_id_str = str(getattr(ord_rec, "connection_id", "") or "").strip() or None
            ext_order_id = str(ord_rec.source_record_id).strip()
            if "/" in ext_order_id and ext_order_id.startswith("gid://"):
                ext_order_id = ext_order_id.rsplit("/", 1)[-1]
            scoped_order_ext = f"{conn_id_str}:{ext_order_id}" if conn_id_str else ext_order_id

            raw_fin = (
                data.get("financial_status")
                if data.get("financial_status") is not None
                else (
                    data.get("payment_status")
                    if data.get("payment_status") is not None
                    else data.get("status")
                )
            )
            fin_status = str(raw_fin).lower().strip() if raw_fin is not None and str(raw_fin).strip() else "unverified"
            if fin_status in {"voided", "cancelled", "canceled"}:
                continue

            gross_total = _to_decimal(
                data.get("total_price") if data.get("total_price") is not None else data.get("total_amount") or data.get("total"),
                default=Decimal("0.00"),
            ) or Decimal("0.00")
            if gross_total <= Decimal("0.00"):
                continue

            documented_tax = _to_decimal(
                data.get("total_tax") if data.get("total_tax") is not None else data.get("tax_amount"),
                default=Decimal("0.00"),
            ) or Decimal("0.00")
            explicit_subtotal = _to_decimal(
                data.get("subtotal_price") if data.get("subtotal_price") is not None else data.get("subtotal"),
                default=None,
            )
            net_subtotal = (
                explicit_subtotal
                if explicit_subtotal is not None
                else max(Decimal("0.00"), (gross_total - documented_tax).quantize(TWOPLACES, rounding=ROUND_HALF_UP))
            )

            currency = str(data.get("currency") or "CAD").upper()[:10]
            order_date = _parse_datetime(
                data.get("order_timestamp")
                or data.get("created_at")
                or data.get("processed_at")
                or data.get("date_created")
                or ord_rec.source_updated_at,
            )
            order_number = str(data.get("order_number") or data.get("name") or f"ORD-{ext_order_id}")[:100]
            customer_name = str(
                data.get("customer_name")
                or (data.get("customer") or {}).get("name")
                or (data.get("customer") or {}).get("email")
                or f"Client {provider.title()} #{order_number}"
            )[:255]

            explicit_paid = _to_decimal(data.get("paid_amount"), default=None)
            is_verified_settlement = fin_status in {"paid", "partially_paid", "refunded", "partially_refunded", "completed"}
            should_confirm = bool(auto_confirm and is_verified_settlement)
            verif_status = "verified_connector" if should_confirm else "to_verify"
            acct_status = "posted" if should_confirm else "proposed"

            if fin_status in {"paid", "refunded", "partially_refunded", "completed"}:
                paid_dec = explicit_paid if explicit_paid is not None else gross_total
            elif fin_status == "partially_paid":
                paid_dec = explicit_paid if explicit_paid is not None else Decimal("0.00")
            else:
                # L'absence de preuve explicite de paiement ne vaut JAMAIS `paid`
                paid_dec = explicit_paid if (explicit_paid is not None and is_verified_settlement) else Decimal("0.00")

            # 1. Facture commerciale liée à la commande (`invoice`)
            inv_idem = f"{conn_ns}:{company_id}:{ext_order_id}:invoice"
            inv = self._get_invoice_by_idempotency(company_id, inv_idem)
            raw_line_items = data.get("line_items") if isinstance(data.get("line_items"), list) else []
            target_inv_status = (
                "paid"
                if (should_confirm and paid_dec >= gross_total)
                else ("partial" if (should_confirm and paid_dec > Decimal("0.00")) else ("unpaid" if should_confirm else "to_verify"))
            )
            if inv is None:
                inv = AccountingInvoice(
                    company_id=company_id,
                    invoice_number=f"ECOM-{order_number}"[:100],
                    invoice_type="receivable",
                    document_nature="customer_invoice",
                    direction="revenue",
                    company_role="issuer_supplier",
                    party_name=customer_name,
                    recipient_name=customer_name,
                    issue_date=order_date,
                    due_date=order_date,
                    subtotal_amount=float(net_subtotal),
                    tax_amount=float(documented_tax),
                    tax_breakdown=data.get("tax_breakdown") if isinstance(data.get("tax_breakdown"), dict) else {},
                    total_amount=float(gross_total),
                    paid_amount=float(paid_dec),
                    currency=currency,
                    status=target_inv_status,
                    is_confirmed=should_confirm,
                    line_items=raw_line_items,
                    source_module="retail",
                    external_id=scoped_order_ext,
                    idempotency_key=inv_idem,
                    verification_status=verif_status,
                    accounting_status=acct_status,
                    confidence_score=1.0 if is_verified_settlement else 0.75,
                    classification_rationale=f"Synchronisation {provider} commande #{order_number} ({fin_status}).",
                    extra_data={
                        "provider": provider,
                        "connection_id": conn_id_str,
                        "commerce_record_id": str(ord_rec.id),
                        "financial_status": fin_status,
                        "order_number": order_number,
                        "order_external_id": ext_order_id,
                    },
                )
                self._session.add(inv)
                self._session.flush()
                created_invoices += 1
            else:
                skipped_idempotent += 1
                if inv.status != "rejected":
                    inv.issue_date = order_date
                    inv.due_date = order_date
                    inv.subtotal_amount = float(net_subtotal)
                    inv.tax_amount = float(documented_tax)
                    inv.total_amount = float(gross_total)
                    inv.paid_amount = float(paid_dec)
                    inv.currency = currency
                    if should_confirm and not inv.is_confirmed:
                        inv.is_confirmed = True
                        inv.verification_status = verif_status
                        inv.accounting_status = acct_status
                        inv.status = target_inv_status
                    elif inv.is_confirmed:
                        inv.status = "paid" if paid_dec >= gross_total else ("partial" if paid_dec > Decimal("0.00") else "unpaid")
            invoice_by_order_ext[scoped_order_ext] = inv
            invoice_by_order_ext.setdefault(ext_order_id, inv)

            # 2. Trace distincte de commande (`order`, non-P&L pour ne jamais doubler le CA)
            order_idem = f"{conn_ns}:{company_id}:{ext_order_id}:order"
            if self._upsert_tx_if_absent(
                company_id=company_id,
                idempotency_key=order_idem,
                transaction_date=order_date,
                transaction_type="order",
                entry_kind="order",
                category="ecommerce_order",
                description=f"Commande {provider.title()} {order_number}",
                amount=float(gross_total),
                subtotal_amount=float(net_subtotal),
                tax_amount=float(documented_tax),
                currency=currency,
                status="confirmed" if should_confirm else "proposed",
                is_confirmed=should_confirm,
                verification_status=verif_status,
                accounting_status=acct_status,
                reference_id=order_number,
                external_id=scoped_order_ext,
                invoice_id=inv.id,
                extra_data={"provider": provider, "connection_id": conn_id_str, "financial_status": fin_status, "non_pnl_memo": True},
            ):
                created_transactions += 1
            else:
                skipped_idempotent += 1

            # 3. Écriture comptable de vente (`journal_entry` / `revenue`)
            sale_idem = f"{conn_ns}:{company_id}:{ext_order_id}:sale_revenue"
            if self._upsert_tx_if_absent(
                company_id=company_id,
                idempotency_key=sale_idem,
                transaction_date=order_date,
                transaction_type="revenue",
                entry_kind="journal_entry",
                category="sales",
                description=f"Vente e-commerce {provider.title()} {order_number}",
                amount=float(net_subtotal),
                subtotal_amount=float(net_subtotal),
                tax_amount=float(documented_tax),
                currency=currency,
                status="confirmed" if should_confirm else "proposed",
                is_confirmed=should_confirm,
                verification_status=verif_status,
                accounting_status=acct_status,
                reference_id=order_number,
                external_id=scoped_order_ext,
                invoice_id=inv.id,
                extra_data={"provider": provider, "connection_id": conn_id_str, "gross_total": float(gross_total)},
            ):
                created_transactions += 1
            else:
                skipped_idempotent += 1

            # 4. Encaissement client distinct (`payment_collected`, type `payment` — ne double jamais `revenue`)
            if paid_dec > Decimal("0.00"):
                pay_ext_id = str(data.get("payment_id") or data.get("gateway_reference") or ext_order_id)
                pay_idem = f"{conn_ns}:{company_id}:{ext_order_id}:{pay_ext_id}:payment_collected"
                if self._upsert_tx_if_absent(
                    company_id=company_id,
                    idempotency_key=pay_idem,
                    transaction_date=order_date,
                    transaction_type="payment",
                    entry_kind="payment_collected",
                    category="settlement",
                    description=f"Encaissement {provider.title()} commande {order_number}",
                    amount=float(paid_dec),
                    subtotal_amount=None,
                    tax_amount=0.0,
                    currency=currency,
                    status="reconciled" if should_confirm else "proposed",
                    is_confirmed=should_confirm,
                    verification_status=verif_status,
                    accounting_status="reconciled" if should_confirm else "proposed",
                    reference_id=order_number,
                    external_id=f"{conn_id_str}:{pay_ext_id}" if conn_id_str else pay_ext_id,
                    invoice_id=inv.id,
                    extra_data={"provider": provider, "connection_id": conn_id_str, "order_external_id": scoped_order_ext},
                ):
                    created_transactions += 1
                else:
                    skipped_idempotent += 1

            # 5. COGS vérifiables uniquement (jamais inventés si absents)
            known_cogs, cogs_complete = self._compute_verifiable_cogs(
                data,
                list(raw_line_items or []),
                product_costs,
                connection_id=conn_id_str,
            )
            if known_cogs is not None and known_cogs > Decimal("0.00"):
                cogs_idem = f"{conn_ns}:{company_id}:{ext_order_id}:cogs"
                if self._upsert_tx_if_absent(
                    company_id=company_id,
                    idempotency_key=cogs_idem,
                    transaction_date=order_date,
                    transaction_type="expense",
                    entry_kind="journal_entry",
                    category="cogs",
                    description=f"COGS vérifié commande {order_number}",
                    amount=float(known_cogs),
                    subtotal_amount=float(known_cogs),
                    tax_amount=0.0,
                    currency=currency,
                    status="confirmed" if should_confirm else "proposed",
                    is_confirmed=should_confirm,
                    verification_status=verif_status,
                    accounting_status=acct_status,
                    reference_id=order_number,
                    external_id=scoped_order_ext,
                    invoice_id=inv.id,
                    extra_data={"cogs_complete": cogs_complete, "provider": provider, "connection_id": conn_id_str},
                ):
                    created_transactions += 1
                else:
                    skipped_idempotent += 1

            # 6. Frais de traitement documentés (`processing_fee` / `gateway_fee`)
            proc_fee = _to_decimal(
                data.get("processing_fee") if data.get("processing_fee") is not None else data.get("gateway_fee"),
                default=None,
            )
            if proc_fee is not None and proc_fee > Decimal("0.00"):
                fee_idem = f"{conn_ns}:{company_id}:{ext_order_id}:processing_fee"
                if self._upsert_tx_if_absent(
                    company_id=company_id,
                    idempotency_key=fee_idem,
                    transaction_date=order_date,
                    transaction_type="expense",
                    entry_kind="journal_entry",
                    category="processing_fees",
                    description=f"Frais de paiement {provider.title()} commande {order_number}",
                    amount=float(proc_fee),
                    subtotal_amount=float(proc_fee),
                    tax_amount=0.0,
                    currency=currency,
                    status="confirmed" if should_confirm else "proposed",
                    is_confirmed=should_confirm,
                    verification_status=verif_status,
                    accounting_status=acct_status,
                    reference_id=order_number,
                    external_id=scoped_order_ext,
                    invoice_id=inv.id,
                    extra_data={"provider": provider, "connection_id": conn_id_str},
                ):
                    created_transactions += 1
                else:
                    skipped_idempotent += 1

            # 7. Remboursements intégrés dans la commande (`data["refunds"]`)
            raw_refunds = data.get("refunds")
            embedded_refunds: list[Any] = raw_refunds if isinstance(raw_refunds, list) else []
            for idx_ref, ref_item in enumerate(embedded_refunds):
                if not isinstance(ref_item, dict):
                    continue
                ref_id = str(ref_item.get("id") or ref_item.get("refund_id") or f"{ext_order_id}-ref-{idx_ref + 1}").strip()
                processed_refund_identities.add(f"{conn_ns}:{ref_id}")
                c_inv, c_tx, s_id = self._sync_single_refund(
                    company_id=company_id,
                    provider=provider,
                    conn_ns=conn_ns,
                    connection_id=conn_id_str,
                    refund_ext_id=ref_id,
                    order_ext_id=scoped_order_ext,
                    order_number=order_number,
                    customer_name=customer_name,
                    currency=currency,
                    refund_data=ref_item,
                    linked_invoice=inv,
                    should_confirm=should_confirm,
                )
                created_invoices += c_inv
                created_transactions += c_tx
                skipped_idempotent += s_id
                if c_tx > 0 or c_inv > 0:
                    refunds_synced += 1

            orders_synced += 1

        # 8. Enregistrements de remboursements autonomes (`entity_type == "refunds"`)
        for ref_rec in standalone_refunds:
            rdata = ref_rec.normalized_data or {}
            provider = (ref_rec.provider or "shopify").lower().strip()
            conn_ns = self._connection_namespace(provider, ref_rec)
            conn_id_str = str(getattr(ref_rec, "connection_id", "") or "").strip() or None
            ref_ext_id = str(ref_rec.source_record_id).strip()
            if "/" in ref_ext_id and ref_ext_id.startswith("gid://"):
                ref_ext_id = ref_ext_id.rsplit("/", 1)[-1]
            _, _, _, _, ord_ext_id = _extract_canonical_refund_fields(rdata, default_date=ref_rec.source_updated_at)
            scoped_ord_ext = (f"{conn_id_str}:{ord_ext_id}" if conn_id_str else ord_ext_id) if ord_ext_id else ""
            linked_inv = invoice_by_order_ext.get(scoped_ord_ext) or invoice_by_order_ext.get(ord_ext_id)
            if linked_inv is None and ord_ext_id:
                linked_inv = self._get_invoice_by_idempotency(
                    company_id, f"{conn_ns}:{company_id}:{ord_ext_id}:invoice"
                )
            c_inv, c_tx, s_id = self._sync_single_refund(
                company_id=company_id,
                provider=provider,
                conn_ns=conn_ns,
                connection_id=conn_id_str,
                refund_ext_id=ref_ext_id,
                order_ext_id=scoped_ord_ext or (f"{conn_id_str}:{ref_ext_id}" if conn_id_str else ref_ext_id),
                order_number=str(rdata.get("order_number") or (linked_inv.invoice_number if linked_inv else None) or ord_ext_id or ref_ext_id),
                customer_name=str(rdata.get("customer_name") or (linked_inv.party_name if linked_inv else None) or "Client e-commerce"),
                currency=str(rdata.get("currency") or (linked_inv.currency if linked_inv else None) or "CAD").upper()[:10],
                refund_data=rdata,
                linked_invoice=linked_inv,
                should_confirm=auto_confirm,
                default_date=ref_rec.source_updated_at,
            )
            created_invoices += c_inv
            created_transactions += c_tx
            skipped_idempotent += s_id
            if c_tx > 0 or c_inv > 0:
                refunds_synced += 1

        self._session.add(
            AuditLogEntry(
                actor_user_id=actor_user_id,
                company_id=company_id,
                action="accounting.integration.retail_sync",
                target_type="NormalizedCommerceRecord",
                target_id=str(company_id),
                safe_metadata={
                    "orders_processed": orders_synced,
                    "refunds_synced": refunds_synced,
                    "created_invoices": created_invoices,
                    "created_transactions": created_transactions,
                    "skipped_idempotent": skipped_idempotent,
                    "auto_confirm_verified_settlements": auto_confirm,
                },
            )
        )
        self._session.commit()

        return {
            "source_module": "retail",
            "orders_processed": orders_synced,
            "refunds_synced": refunds_synced,
            "created_invoices": created_invoices,
            "created_transactions": created_transactions,
            "skipped_idempotent": skipped_idempotent,
            "governance_mode": "verified_connector_confirmed" if auto_confirm else "proposed_to_verify",
        }

    def _sync_single_refund(
        self,
        *,
        company_id: UUID,
        provider: str,
        conn_ns: str | None = None,
        connection_id: str | None = None,
        refund_ext_id: str,
        order_ext_id: str,
        order_number: str,
        customer_name: str,
        currency: str,
        refund_data: dict[str, Any],
        linked_invoice: AccountingInvoice | None,
        should_confirm: bool,
        default_date: Any = None,
    ) -> tuple[int, int, int]:
        ref_gross, ref_tax, ref_sub, ref_date, _ = _extract_canonical_refund_fields(
            refund_data,
            default_date=default_date,
        )
        if ref_gross <= Decimal("0.00"):
            return 0, 0, 0

        eff_ns = conn_ns or provider
        verif_status = "verified_connector" if should_confirm else "to_verify"
        acct_status = "posted" if should_confirm else "proposed"

        c_inv = 0
        c_tx = 0
        skipped = 0

        cn_idem = f"{eff_ns}:{company_id}:{refund_ext_id}:credit_note"
        cn_inv = self._get_invoice_by_idempotency(company_id, cn_idem)
        if cn_inv is None:
            cn_inv = AccountingInvoice(
                company_id=company_id,
                invoice_number=f"CN-{order_number}-{refund_ext_id[-6:]}"[:100],
                invoice_type="credit_note",
                document_nature="credit_note",
                direction="revenue_reversal",
                company_role="issuer_supplier",
                party_name=customer_name,
                recipient_name=customer_name,
                issue_date=ref_date,
                due_date=ref_date,
                subtotal_amount=float(ref_sub),
                tax_amount=float(ref_tax),
                total_amount=float(ref_gross),
                paid_amount=float(ref_gross),
                currency=currency,
                status="posted" if should_confirm else "to_verify",
                is_confirmed=should_confirm,
                source_module="retail",
                external_id=f"{connection_id}:{refund_ext_id}" if connection_id else refund_ext_id,
                idempotency_key=cn_idem,
                verification_status=verif_status,
                accounting_status=acct_status,
                confidence_score=1.0,
                classification_rationale=f"Avoir / remboursement {provider} #{refund_ext_id} sur commande {order_number} (jamais une vente).",
                extra_data={
                    "provider": provider,
                    "connection_id": connection_id,
                    "order_external_id": order_ext_id,
                    "original_invoice_id": str(linked_invoice.id) if linked_invoice else None,
                },
            )
            self._session.add(cn_inv)
            self._session.flush()
            c_inv += 1
        else:
            skipped += 1
            if cn_inv.status != "rejected":
                cn_inv.issue_date = ref_date
                cn_inv.due_date = ref_date
                cn_inv.subtotal_amount = float(ref_sub)
                cn_inv.tax_amount = float(ref_tax)
                cn_inv.total_amount = float(ref_gross)
                cn_inv.paid_amount = float(ref_gross)
                if should_confirm and not cn_inv.is_confirmed:
                    cn_inv.is_confirmed = True
                    cn_inv.verification_status = verif_status
                    cn_inv.accounting_status = acct_status
                    cn_inv.status = "posted"

        # Lier l'écriture de remboursement directement à la note de crédit `cn_inv.id` (et conserver la facture d'origine dans extra_data)
        # afin que la révision ultérieure de `cn_inv` ne crée jamais un second remboursement en double.
        ref_idem = f"{eff_ns}:{company_id}:{refund_ext_id}:refund"
        if self._upsert_tx_if_absent(
            company_id=company_id,
            idempotency_key=ref_idem,
            transaction_date=ref_date,
            transaction_type="refund",
            entry_kind="refund",
            category="sales_returns",
            description=f"Remboursement client {provider.title()} #{refund_ext_id} (commande {order_number})",
            amount=float(ref_sub),
            subtotal_amount=float(ref_sub),
            tax_amount=float(ref_tax),
            currency=currency,
            status="confirmed" if should_confirm else "proposed",
            is_confirmed=should_confirm,
            verification_status=verif_status,
            accounting_status=acct_status,
            reference_id=order_number,
            external_id=f"{connection_id}:{refund_ext_id}" if connection_id else refund_ext_id,
            invoice_id=cn_inv.id,
            extra_data={
                "provider": provider,
                "connection_id": connection_id,
                "order_external_id": order_ext_id,
                "gross_refund_amount": float(ref_gross),
                "direction": "revenue_reversal",
                "credit_note_id": str(cn_inv.id),
                "original_invoice_id": str(linked_invoice.id) if linked_invoice else None,
            },
        ):
            c_tx += 1
        else:
            skipped += 1

        return c_inv, c_tx, skipped

    @staticmethod
    def _compute_verifiable_cogs(
        order_data: dict[str, Any],
        line_items: list[Any],
        product_costs: dict[str, Decimal],
        *,
        connection_id: str | None = None,
    ) -> tuple[Decimal | None, bool]:
        explicit_cogs = _to_decimal(order_data.get("total_cogs") or order_data.get("cogs"), default=None)
        if explicit_cogs is not None and explicit_cogs >= Decimal("0.00"):
            return explicit_cogs, True
        if not line_items:
            return None, False

        accumulated = Decimal("0.00")
        any_found = False
        all_found = True
        for item in line_items:
            if not isinstance(item, dict):
                continue
            qty = _to_decimal(item.get("quantity", 1), default=Decimal("1.00")) or Decimal("1.00")
            unit_cost = _to_decimal(item.get("unit_cost") or item.get("cost"), default=None)
            if unit_cost is None:
                pid = str(item.get("product_id") or "")
                sku = str(item.get("sku") or "")
                if connection_id:
                    unit_cost = (
                        product_costs.get(f"{connection_id}:{pid}")
                        or (product_costs.get(f"{connection_id}:sku:{sku}") if sku else None)
                    )
                if unit_cost is None:
                    unit_cost = product_costs.get(pid) or (product_costs.get(f"sku:{sku}") if sku else None)
            if unit_cost is not None:
                any_found = True
                accumulated += (qty * unit_cost).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
            else:
                all_found = False
        return (accumulated if any_found else None), (any_found and all_found)

    def _get_invoice_by_idempotency(self, company_id: UUID, idempotency_key: str) -> AccountingInvoice | None:
        return self._session.scalar(
            select(AccountingInvoice).where(
                AccountingInvoice.company_id == company_id,
                AccountingInvoice.idempotency_key == idempotency_key,
            )
        )

    def _upsert_tx_if_absent(
        self,
        *,
        company_id: UUID,
        idempotency_key: str,
        transaction_date: datetime,
        transaction_type: str,
        entry_kind: str,
        category: str,
        description: str,
        amount: float,
        subtotal_amount: float | None,
        tax_amount: float,
        currency: str,
        status: str,
        is_confirmed: bool,
        verification_status: str,
        accounting_status: str,
        reference_id: str | None,
        external_id: str | None,
        invoice_id: UUID | None,
        extra_data: dict[str, Any],
    ) -> bool:
        existing = self._session.scalar(
            select(AccountingTransaction).where(
                AccountingTransaction.company_id == company_id,
                AccountingTransaction.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            if existing.status != "rejected":
                existing.transaction_date = transaction_date
                existing.amount = round(amount, 2)
                existing.subtotal_amount = round(subtotal_amount, 2) if subtotal_amount is not None else None
                existing.tax_amount = round(tax_amount, 2)
                existing.currency = currency
                if invoice_id is not None and existing.invoice_id is None:
                    existing.invoice_id = invoice_id
                if is_confirmed and not existing.is_confirmed:
                    existing.is_confirmed = True
                    existing.status = status
                    existing.verification_status = verification_status
                    existing.accounting_status = accounting_status
            return False
        tx = AccountingTransaction(
            company_id=company_id,
            transaction_date=transaction_date,
            transaction_type=transaction_type,
            entry_kind=entry_kind,
            category=category,
            description=description[:255],
            amount=round(amount, 2),
            subtotal_amount=round(subtotal_amount, 2) if subtotal_amount is not None else None,
            currency=currency,
            status=status,
            is_confirmed=is_confirmed,
            tax_amount=round(tax_amount, 2),
            reference_id=reference_id[:100] if reference_id else None,
            source_module="retail",
            external_id=external_id,
            idempotency_key=idempotency_key,
            invoice_id=invoice_id,
            verification_status=verification_status,
            accounting_status=accounting_status,
            confidence_score=1.0,
            extra_data=extra_data,
        )
        self._session.add(tx)
        self._session.flush()
        return True

    def sync_crm_billables_to_accounting(
        self,
        company_id: UUID,
        *,
        actor_user: User,
    ) -> dict[str, Any]:
        """Crée des propositions de factures clients (`to_verify`) depuis les rendez-vous CRM complétés."""
        tenant = TenantContext(company_id=company_id, user_id=actor_user.id)
        if not ModuleEntitlementService(self._session).can_use_module(tenant, "crm"):
            return {"available": False, "reason": "crm_module_inactive", "created_proposals": 0}

        completed_appts = list(
            self._session.scalars(
                select(CRMAppointment).where(
                    CRMAppointment.company_id == company_id,
                    CRMAppointment.is_deleted.is_(False),
                    CRMAppointment.status == "completed",
                    CRMAppointment.price > 0,
                )
            ).all()
        )
        clients_by_id = {
            c.id: c
            for c in self._session.scalars(
                select(CRMClient).where(CRMClient.company_id == company_id)
            ).all()
        }

        created_count = 0
        skipped_count = 0
        for appt in completed_appts:
            idem = f"crm:{company_id}:appointment:{appt.id}:invoice"
            if self._get_invoice_by_idempotency(company_id, idem) is not None:
                skipped_count += 1
                continue
            client = clients_by_id.get(appt.client_id)
            client_name = client.full_name if client else "Client CRM"
            inv = AccountingInvoice(
                company_id=company_id,
                invoice_number=f"CRM-{str(appt.id)[:8].upper()}",
                invoice_type="receivable",
                document_nature="customer_invoice",
                direction="revenue",
                company_role="issuer_supplier",
                party_name=client_name[:255],
                recipient_name=client_name[:255],
                issue_date=appt.end_time or appt.start_time,
                due_date=(appt.end_time or appt.start_time) + timedelta(days=15),
                subtotal_amount=round(appt.price, 2),
                tax_amount=0.0,
                total_amount=round(appt.price, 2),
                paid_amount=0.0,
                currency=(appt.currency or "CAD").upper()[:10],
                status="to_verify",
                is_confirmed=False,
                source_module="crm",
                external_id=str(appt.id),
                idempotency_key=idem,
                verification_status="to_verify",
                accounting_status="proposed",
                confidence_score=0.92,
                classification_rationale=f"Proposition de facturation issue du rendez-vous CRM complété '{appt.title}'.",
                line_items=[
                    {
                        "line_index": 1,
                        "description": appt.title,
                        "quantity": "1.00",
                        "unit_price": f"{appt.price:.2f}",
                        "total": f"{appt.price:.2f}",
                    }
                ],
                extra_data={
                    "crm_appointment_id": str(appt.id),
                    "crm_client_id": str(appt.client_id),
                },
            )
            self._session.add(inv)
            created_count += 1

        self._session.commit()
        return {
            "available": True,
            "source_module": "crm",
            "completed_appointments_scanned": len(completed_appts),
            "created_proposals": created_count,
            "skipped_idempotent": skipped_count,
            "governance_mode": "proposed_to_verify",
        }

    def get_hr_payroll_summary(
        self,
        company_id: UUID,
        *,
        actor_user: User | None,
        strict_raise: bool = False,
    ) -> dict[str, Any]:
        """Retourne UNIQUEMENT la masse salariale agrégée lorsque HR AI est actif et le rôle autorisé."""
        allowed, reason = can_access_hr_payroll_summary(self._session, company_id, actor_user)
        if not allowed:
            if strict_raise:
                raise HRPayrollAccessDeniedError(
                    f"Accès refusé aux coûts salariaux RH ({reason}). "
                    "Nécessite le module HR AI actif et un rôle exécutif/direction autorisé."
                )
            return {
                "available": False,
                "access_granted": False,
                "reason": reason,
            }

        payroll_txs = list(
            self._session.scalars(
                select(AccountingTransaction).where(
                    AccountingTransaction.company_id == company_id,
                    AccountingTransaction.transaction_type == "expense",
                    AccountingTransaction.category.in_(["payroll", "salaries", "salaires", "employer_taxes"]),
                    AccountingTransaction.is_confirmed.is_(True),
                )
            ).all()
        )
        active_staff_rows = list(
            self._session.scalars(
                select(User).where(
                    User.company_id == company_id,
                    User.is_active.is_(True),
                )
            ).all()
        )

        by_department: dict[str, float] = defaultdict(float)
        for tx in payroll_txs:
            dept = str((tx.extra_data or {}).get("department") or "Non ventilé")
            by_department[dept] += tx.amount

        total_payroll = round(sum(t.amount for t in payroll_txs), 2)
        return {
            "available": True,
            "access_granted": True,
            "aggregation_level": "company_and_department_totals_only",
            "personal_records_exposed": False,
            "active_headcount": len(active_staff_rows),
            "confirmed_payroll_entries_count": len(payroll_txs),
            "total_confirmed_payroll_cost": total_payroll,
            "department_payroll_breakdown": [
                {"department": dept, "amount": round(amt, 2)}
                for dept, amt in sorted(by_department.items(), key=lambda x: x[1], reverse=True)
            ],
            "currency": payroll_txs[0].currency if payroll_txs else "CAD",
        }

    def get_unified_financial_context(
        self,
        company_id: UUID,
        *,
        actor_user: User | None = None,
    ) -> dict[str, Any]:
        """Vue unifiée multi-modules respectant les activations de modules et le RBAC de l'appelant."""
        tenant = TenantContext(company_id=company_id, user_id=actor_user.id if actor_user else None)
        entitlements = ModuleEntitlementService(self._session)
        held_perms = set(effective_permissions(actor_user)) if actor_user is not None else set()

        # Retail AI summary
        retail_active = entitlements.can_use_module(tenant, "retail")
        retail_summary: dict[str, Any] = {"module_active": retail_active}
        if retail_active and (actor_user is None or held_perms.intersection({"retail:read", "accounting:read", "data:read"})):
            reconciliation = self.reconcile_ecommerce_and_accounting(company_id)
            retail_summary.update({
                "orders_count": reconciliation["commerce_orders_count"],
                "gross_sales_total": reconciliation["commerce_sales_total"],
                "net_sales_total": reconciliation["commerce_net_sales_total"],
                "documented_taxes_total": reconciliation["commerce_taxes_total"],
                "refunds_total": reconciliation["commerce_refunds_total"],
                "reconciliation_status": reconciliation["status"],
            })

        # CRM AI summary
        crm_active = entitlements.can_use_module(tenant, "crm")
        crm_summary: dict[str, Any] = {"module_active": crm_active}
        if crm_active and (
            actor_user is None or held_perms.intersection({"crm:clients:read", "crm:appointments:read", "accounting:read"})
        ):
            clients_count = len(
                self._session.scalars(
                    select(CRMClient.id).where(
                        CRMClient.company_id == company_id,
                        CRMClient.is_deleted.is_(False),
                        CRMClient.is_synthetic.is_(False),
                    )
                ).all()
            )
            completed_appts = list(
                self._session.scalars(
                    select(CRMAppointment).where(
                        CRMAppointment.company_id == company_id,
                        CRMAppointment.is_deleted.is_(False),
                        CRMAppointment.status == "completed",
                    )
                ).all()
            )
            signed_contracts_count = len(
                self._session.scalars(
                    select(CompanyContract.id).where(CompanyContract.company_id == company_id)
                ).all()
            )
            crm_summary.update({
                "active_clients_count": clients_count,
                "completed_billable_appointments_count": len(completed_appts),
                "completed_appointments_value": round(sum(a.price for a in completed_appts), 2),
                "contracts_count": signed_contracts_count,
            })

        # OCR / Documents summary
        ocr_docs_count = len(
            self._session.scalars(
                select(TenantDocument.id).where(
                    TenantDocument.company_id == company_id,
                    TenantDocument.kind == "ocr",
                )
            ).all()
        )
        pending_proposals = list(
            self._session.scalars(
                select(AccountingInvoice).where(
                    AccountingInvoice.company_id == company_id,
                    AccountingInvoice.verification_status == "to_verify",
                )
            ).all()
        )

        # HR AI summary (strictement cloisonné)
        hr_summary = self.get_hr_payroll_summary(company_id, actor_user=actor_user, strict_raise=False)

        return {
            "scope": "company_wide",
            "scope_note": "Cross-module company totals, not filtered to the selected dataset. Do not combine with dataset-scoped ledger totals.",
            "retail": retail_summary,
            "crm": crm_summary,
            "ocr_documents": {
                "ocr_documents_count": ocr_docs_count,
                "pending_to_verify_invoices_count": len(pending_proposals),
                "duplicate_warnings_count": sum(1 for inv in pending_proposals if inv.duplicate_warning),
            },
            "hr_payroll": hr_summary,
        }

    def reconcile_ecommerce_and_accounting(self, company_id: UUID) -> dict[str, Any]:
        """Réconciliation granulaire entre ventes e-commerce, paiements encaissés, factures et remboursements Retail AI."""
        orders = list(
            self._session.scalars(
                select(NormalizedCommerceRecord).where(
                    NormalizedCommerceRecord.company_id == company_id,
                    NormalizedCommerceRecord.entity_type == "orders",
                    NormalizedCommerceRecord.deleted.is_(False),
                    NormalizedCommerceRecord.is_demo.is_(False),
                )
            ).all()
        )
        standalone_refunds = list(
            self._session.scalars(
                select(NormalizedCommerceRecord).where(
                    NormalizedCommerceRecord.company_id == company_id,
                    NormalizedCommerceRecord.entity_type == "refunds",
                    NormalizedCommerceRecord.deleted.is_(False),
                    NormalizedCommerceRecord.is_demo.is_(False),
                )
            ).all()
        )

        # Limiter strictement les transactions et factures à la provenance Retail (`source_module == 'retail'`)
        # pour qu'une facture CRM, manuelle ou OCR ne crée jamais un faux écart e-commerce.
        txs = list(
            self._session.scalars(
                select(AccountingTransaction).where(
                    AccountingTransaction.company_id == company_id,
                    AccountingTransaction.source_module == "retail",
                )
            ).all()
        )
        invoices = list(
            self._session.scalars(
                select(AccountingInvoice).where(
                    AccountingInvoice.company_id == company_id,
                    AccountingInvoice.source_module == "retail",
                )
            ).all()
        )

        commerce_gross_sales = Decimal("0.00")
        commerce_taxes = Decimal("0.00")
        commerce_net_sales = Decimal("0.00")
        commerce_refunds_gross = Decimal("0.00")
        commerce_refunds_net = Decimal("0.00")
        expected_payments_total = Decimal("0.00")

        inv_by_ext: dict[str, AccountingInvoice] = {}
        for inv in invoices:
            if inv.invoice_type == "receivable" and inv.external_id:
                inv_by_ext[inv.external_id] = inv
                raw_ord_ext = (inv.extra_data or {}).get("order_external_id")
                if raw_ord_ext:
                    inv_by_ext.setdefault(str(raw_ord_ext), inv)

        txs_by_ext: dict[str, list[AccountingTransaction]] = defaultdict(list)
        for tx in txs:
            if tx.external_id:
                txs_by_ext[tx.external_id].append(tx)
            order_ext = (tx.extra_data or {}).get("order_external_id")
            if order_ext and order_ext != tx.external_id:
                txs_by_ext[str(order_ext)].append(tx)

        matched_orders: list[dict[str, Any]] = []
        pending_approval_orders: list[dict[str, Any]] = []
        unlinked_orders: list[dict[str, Any]] = []
        seen_refund_keys: set[str] = set()

        for ord_rec in orders:
            data = ord_rec.normalized_data or {}
            provider = (ord_rec.provider or "shopify").lower().strip()
            conn_ns = self._connection_namespace(provider, ord_rec)
            conn_id_str = str(getattr(ord_rec, "connection_id", "") or "").strip() or None
            ext_id = str(ord_rec.source_record_id).strip()
            if "/" in ext_id and ext_id.startswith("gid://"):
                ext_id = ext_id.rsplit("/", 1)[-1]
            scoped_ext = f"{conn_id_str}:{ext_id}" if conn_id_str else ext_id

            raw_fin = (
                data.get("financial_status")
                if data.get("financial_status") is not None
                else (
                    data.get("payment_status")
                    if data.get("payment_status") is not None
                    else data.get("status")
                )
            )
            fin_status = str(raw_fin).lower().strip() if raw_fin is not None and str(raw_fin).strip() else "unverified"
            if fin_status in {"voided", "cancelled", "canceled"}:
                continue

            gross = _to_decimal(
                data.get("total_price") if data.get("total_price") is not None else data.get("total_amount") or data.get("total"),
                default=Decimal("0.00"),
            ) or Decimal("0.00")
            tax = _to_decimal(
                data.get("total_tax") if data.get("total_tax") is not None else data.get("tax_amount"),
                default=Decimal("0.00"),
            ) or Decimal("0.00")
            sub = _to_decimal(
                data.get("subtotal_price") if data.get("subtotal_price") is not None else data.get("subtotal"),
                default=None,
            )
            if sub is None:
                sub = max(Decimal("0.00"), gross - tax)

            commerce_gross_sales += gross
            commerce_taxes += tax
            commerce_net_sales += sub

            explicit_paid = _to_decimal(data.get("paid_amount"), default=None)
            if fin_status in {"paid", "refunded", "partially_refunded", "completed"}:
                expected_order_paid = explicit_paid if explicit_paid is not None else gross
            elif fin_status == "partially_paid":
                expected_order_paid = explicit_paid if explicit_paid is not None else Decimal("0.00")
            else:
                expected_order_paid = Decimal("0.00")
            expected_payments_total += expected_order_paid

            for idx_ref, ref in enumerate(data.get("refunds") or []):
                if isinstance(ref, dict):
                    ref_id = str(ref.get("id") or ref.get("refund_id") or f"{ext_id}-ref-{idx_ref + 1}").strip()
                    dedup_key = f"{conn_ns}:{ref_id}"
                    if dedup_key in seen_refund_keys:
                        continue
                    seen_refund_keys.add(dedup_key)
                    rg, _, rs, _, _ = _extract_canonical_refund_fields(ref)
                    commerce_refunds_gross += rg
                    commerce_refunds_net += rs

            linked_inv = inv_by_ext.get(scoped_ext) or inv_by_ext.get(ext_id)
            order_txs = list(txs_by_ext.get(scoped_ext, []))
            if scoped_ext != ext_id:
                for extra_tx in txs_by_ext.get(ext_id, []):
                    if extra_tx not in order_txs:
                        order_txs.append(extra_tx)
            if linked_inv is not None:
                for tx_cand in txs:
                    if tx_cand.invoice_id == linked_inv.id and tx_cand not in order_txs:
                        order_txs.append(tx_cand)

            rev_txs = [t for t in order_txs if t.transaction_type == "revenue" and t.status != "rejected"]
            pay_txs = [t for t in order_txs if t.entry_kind == "payment_collected" and t.status != "rejected"]
            confirmed_order_rev = sum((Decimal(str(t.amount)) for t in rev_txs if t.is_confirmed), Decimal("0.00"))
            confirmed_order_pay = sum((Decimal(str(t.amount)) for t in pay_txs if t.is_confirmed), Decimal("0.00"))

            item_summary = {
                "order_external_id": scoped_ext,
                "financial_status": fin_status,
                "gross_amount": float(gross),
                "net_amount": float(sub),
                "tax_amount": float(tax),
                "expected_paid_amount": float(expected_order_paid),
                "invoice_id": str(linked_inv.id) if linked_inv else None,
                "revenue_transaction_ids": [str(t.id) for t in rev_txs],
                "payment_transaction_ids": [str(t.id) for t in pay_txs],
            }
            if linked_inv is None or not rev_txs or (expected_order_paid > Decimal("0.00") and not pay_txs):
                unlinked_orders.append(item_summary)
            elif (
                not linked_inv.is_confirmed
                or any(not t.is_confirmed for t in rev_txs)
                or (expected_order_paid > Decimal("0.00") and any(not t.is_confirmed for t in pay_txs))
            ):
                pending_approval_orders.append(item_summary)
            elif (
                abs(confirmed_order_rev - sub) > Decimal("0.02")
                or abs(Decimal(str(linked_inv.total_amount)) - gross) > Decimal("0.02")
                or (expected_order_paid > Decimal("0.00") and abs(confirmed_order_pay - expected_order_paid) > Decimal("0.02"))
            ):
                unlinked_orders.append(item_summary)
            else:
                matched_orders.append(item_summary)

        for ref_rec in standalone_refunds:
            rdata = ref_rec.normalized_data or {}
            provider = (ref_rec.provider or "shopify").lower().strip()
            conn_ns = self._connection_namespace(provider, ref_rec)
            ref_id = str(ref_rec.source_record_id).strip()
            if "/" in ref_id and ref_id.startswith("gid://"):
                ref_id = ref_id.rsplit("/", 1)[-1]
            dedup_key = f"{conn_ns}:{ref_id}"
            if dedup_key in seen_refund_keys:
                continue
            seen_refund_keys.add(dedup_key)
            rg, _, rs, _, _ = _extract_canonical_refund_fields(rdata, default_date=ref_rec.source_updated_at)
            commerce_refunds_gross += rg
            commerce_refunds_net += rs

        confirmed_rev_txs = [t for t in txs if t.transaction_type == "revenue" and t.is_confirmed]
        confirmed_refund_txs = [
            t for t in txs
            if t.transaction_type in {"refund", "credit_note"}
            and t.is_confirmed
            and (t.category in {"sales_returns", "revenue_reversal"} or (t.extra_data or {}).get("direction") == "revenue_reversal")
        ]
        confirmed_payments = [t for t in txs if t.entry_kind == "payment_collected" and t.is_confirmed]
        proposed_rev_txs = [t for t in txs if t.transaction_type == "revenue" and not t.is_confirmed and t.status != "rejected"]

        acct_gross_revenue = sum((Decimal(str(t.amount)) for t in confirmed_rev_txs), Decimal("0.00"))
        acct_sales_tax = sum((Decimal(str(t.tax_amount or 0.0)) for t in confirmed_rev_txs), Decimal("0.00"))
        acct_refunds_net = sum((Decimal(str(t.amount)) for t in confirmed_refund_txs), Decimal("0.00"))
        acct_refunds_tax = sum((Decimal(str(t.tax_amount or 0.0)) for t in confirmed_refund_txs), Decimal("0.00"))
        acct_payments_total = sum((Decimal(str(t.amount)) for t in confirmed_payments), Decimal("0.00"))

        acct_net_revenue = (acct_gross_revenue - acct_refunds_net).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        acct_net_tax = (acct_sales_tax - acct_refunds_tax).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        acct_gross_with_tax = (acct_net_revenue + acct_net_tax).quantize(TWOPLACES, rounding=ROUND_HALF_UP)

        expected_commerce_gross_after_refunds = (commerce_gross_sales - commerce_refunds_gross).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        expected_commerce_net_after_refunds = (commerce_net_sales - commerce_refunds_net).quantize(TWOPLACES, rounding=ROUND_HALF_UP)

        discrepancy_gross = float((expected_commerce_gross_after_refunds - acct_gross_with_tax).quantize(TWOPLACES, rounding=ROUND_HALF_UP))
        discrepancy_net = float((expected_commerce_net_after_refunds - acct_net_revenue).quantize(TWOPLACES, rounding=ROUND_HALF_UP))
        payment_discrepancy = float((expected_payments_total - acct_payments_total).quantize(TWOPLACES, rounding=ROUND_HALF_UP))
        is_reconciled = (
            abs(discrepancy_gross) < 0.01
            and abs(discrepancy_net) < 0.01
            and abs(payment_discrepancy) < 0.01
            and not unlinked_orders
            and not pending_approval_orders
        )

        return {
            "data_type": "reconciliation_audit",
            "is_projection": False,
            "commerce_orders_count": len(orders),
            "commerce_sales_total": float(expected_commerce_gross_after_refunds),
            "commerce_gross_orders_total": float(commerce_gross_sales),
            "commerce_net_sales_total": float(expected_commerce_net_after_refunds),
            "commerce_taxes_total": float(commerce_taxes),
            "commerce_refunds_total": float(commerce_refunds_gross),
            "accounting_transactions_count": len(confirmed_rev_txs),
            "accounting_revenue_total": float(acct_gross_with_tax) if commerce_taxes > Decimal("0.00") else float(acct_net_revenue),
            "accounting_net_revenue_total": float(acct_net_revenue),
            "accounting_documented_sales_tax_total": float(acct_net_tax),
            "accounting_refunds_total": float(acct_refunds_net),
            "accounting_payments_collected_total": round(sum(t.amount for t in confirmed_payments), 2),
            "proposed_pending_revenue_total": round(sum(t.amount for t in proposed_rev_txs), 2),
            "matched_orders_count": len(matched_orders),
            "pending_approval_orders_count": len(pending_approval_orders),
            "unlinked_orders_count": len(unlinked_orders),
            "matched_orders": matched_orders[:50],
            "pending_approval_orders": pending_approval_orders[:50],
            "unlinked_orders": unlinked_orders[:50],
            "discrepancy_amount": discrepancy_gross,
            "net_discrepancy_amount": discrepancy_net,
            "reconciled": is_reconciled,
            "status": "reconciled" if is_reconciled else ("pending_verification" if pending_approval_orders and not unlinked_orders else "discrepancy_detected"),
            "explanation": (
                "Les ventes e-commerce nettes, taxes, encaissements et remboursements correspondent exactement aux écritures comptables confirmées."
                if is_reconciled
                else (
                    f"Écart réel de {abs(discrepancy_gross):.2f} CAD détecté entre les ventes e-commerce nettes de remboursements "
                    f"({float(expected_commerce_gross_after_refunds):.2f} CAD) et les écritures comptables confirmées "
                    f"({float(acct_gross_with_tax):.2f} CAD). Commandes en attente de validation: {len(pending_approval_orders)}, non liées: {len(unlinked_orders)}."
                )
            ),
        }
