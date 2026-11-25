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
from backend.app.models.accounting import (
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
from backend.app.services.accounting_classification_service import (
     TWOPLACES,
    _parse_datetime,
    _to_decimal,
)
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from shared.ai_engine.contracts import TenantContext


class HRPayrollAccessDeniedError(PermissionError):
    """Accès refusé aux données agrégées de masse salariale RH."""


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
                costs[str(prod.source_record_id)] = dec_cost
                if pdata.get("sku"):
                    costs[f"sku:{pdata['sku']}"] = dec_cost
        return costs

    def sync_retail_commerce_to_accounting(
        self,
        company_id: UUID,
        *,
        actor_user_id: UUID | None = None,
        confirm_verified_settlements: bool | None = None,
        include_demo: bool = False,
    ) -> dict[str, Any]:
        """Synchronise commandes, ventes, paiements, taxes, COGS connus, frais et remboursements Retail AI.

        Utilise des `idempotency_key` déterministes (`{provider}:{company_id}:{ext_id}:{event_type}`)
        garantissant ZÉRO double comptage lors d'appels multiples de synchronisation Shopify/WooCommerce.
        """
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

        for ord_rec in order_records:
            data = ord_rec.normalized_data or {}
            provider = (ord_rec.provider or "shopify").lower().strip()
            ext_order_id = str(ord_rec.source_record_id).strip()
            fin_status = str(data.get("financial_status") or data.get("status") or "paid").lower().strip()
            if fin_status in {"voided", "cancelled", "canceled"} and not data.get("total_price"):
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
                data.get("created_at") or data.get("processed_at") or ord_rec.source_updated_at,
            )
            order_number = str(data.get("order_number") or data.get("name") or f"ORD-{ext_order_id}")[:100]
            customer_name = str(
                data.get("customer_name")
                or (data.get("customer") or {}).get("name")
                or (data.get("customer") or {}).get("email")
                or f"Client {provider.title()} #{order_number}"
            )[:255]

            is_verified_settlement = fin_status in {"paid", "partially_paid", "refunded", "partially_refunded", "completed"}
            should_confirm = bool(auto_confirm and is_verified_settlement)
            verif_status = "verified_connector" if should_confirm else "to_verify"
            acct_status = "posted" if should_confirm else "proposed"

            paid_dec = gross_total if fin_status in {"paid", "refunded", "partially_refunded", "completed"} else (
                _to_decimal(data.get("paid_amount"), default=Decimal("0.00")) or Decimal("0.00")
            )

            # 1. Facture commerciale liée à la commande (`invoice`)
            inv_idem = f"{provider}:{company_id}:{ext_order_id}:invoice"
            inv = self._get_invoice_by_idempotency(company_id, inv_idem)
            raw_line_items = data.get("line_items") if isinstance(data.get("line_items"), list) else []
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
                    status="paid" if (should_confirm and paid_dec >= gross_total) else ("unpaid" if should_confirm else "to_verify"),
                    is_confirmed=should_confirm,
                    line_items=raw_line_items,
                    source_module="retail",
                    external_id=ext_order_id,
                    idempotency_key=inv_idem,
                    verification_status=verif_status,
                    accounting_status=acct_status,
                    confidence_score=1.0,
                    classification_rationale=f" Synchronisation {provider} commande #{order_number} ({fin_status}).".strip(),
                    extra_data={
                        "provider": provider,
                        "commerce_record_id": str(ord_rec.id),
                        "financial_status": fin_status,
                        "order_number": order_number,
                    },
                )
                self._session.add(inv)
                self._session.flush()
                created_invoices += 1
            else:
                skipped_idempotent += 1
            invoice_by_order_ext[ext_order_id] = inv

            # 2. Trace distincte de commande (`order`, non-P&L pour ne jamais doubler le CA)
            order_idem = f"{provider}:{company_id}:{ext_order_id}:order"
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
                external_id=ext_order_id,
                invoice_id=inv.id,
                extra_data={"provider": provider, "financial_status": fin_status, "non_pnl_memo": True},
            ):
                created_transactions += 1
            else:
                skipped_idempotent += 1

            # 3. Écriture comptable de vente (`journal_entry` / `revenue`)
            sale_idem = f"{provider}:{company_id}:{ext_order_id}:sale_revenue"
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
                external_id=ext_order_id,
                invoice_id=inv.id,
                extra_data={"provider": provider, "gross_total": float(gross_total)},
            ):
                created_transactions += 1
            else:
                skipped_idempotent += 1

            # 4. Encaissement client distinct (`payment_collected`, type `payment` — ne double jamais `revenue`)
            if paid_dec > Decimal("0.00"):
                pay_ext_id = str(data.get("payment_id") or data.get("gateway_reference") or ext_order_id)
                pay_idem = f"{provider}:{company_id}:{ext_order_id}:{pay_ext_id}:payment_collected"
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
                    external_id=pay_ext_id,
                    invoice_id=inv.id,
                    extra_data={"provider": provider, "order_external_id": ext_order_id},
                ):
                    created_transactions += 1
                else:
                    skipped_idempotent += 1

            # 5. COGS vérifiables uniquement (jamais inventés si absents)
            known_cogs, cogs_complete = self._compute_verifiable_cogs(data, list(raw_line_items or []), product_costs)
            if known_cogs is not None and known_cogs > Decimal("0.00"):
                cogs_idem = f"{provider}:{company_id}:{ext_order_id}:cogs"
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
                    external_id=ext_order_id,
                    invoice_id=inv.id,
                    extra_data={"cogs_complete": cogs_complete, "provider": provider},
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
                fee_idem = f"{provider}:{company_id}:{ext_order_id}:processing_fee"
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
                    external_id=ext_order_id,
                    invoice_id=inv.id,
                    extra_data={"provider": provider},
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
                ref_id = str(ref_item.get("id") or ref_item.get("refund_id") or f"{ext_order_id}-ref-{idx_ref + 1}")
                c_inv, c_tx, s_id = self._sync_single_refund(
                    company_id=company_id,
                    provider=provider,
                    refund_ext_id=ref_id,
                    order_ext_id=ext_order_id,
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
            ref_ext_id = str(ref_rec.source_record_id).strip()
            ord_ext_id = str(rdata.get("order_id") or "").strip()
            linked_inv = invoice_by_order_ext.get(ord_ext_id)
            if linked_inv is None and ord_ext_id:
                linked_inv = self._get_invoice_by_idempotency(
                    company_id, f"{provider}:{company_id}:{ord_ext_id}:invoice"
                )
            c_inv, c_tx, s_id = self._sync_single_refund(
                company_id=company_id,
                provider=provider,
                refund_ext_id=ref_ext_id,
                order_ext_id=ord_ext_id or ref_ext_id,
                order_number=str(rdata.get("order_number") or ord_ext_id or ref_ext_id),
                customer_name=str(rdata.get("customer_name") or "Client e-commerce"),
                currency=str(rdata.get("currency") or "CAD").upper()[:10],
                refund_data=rdata,
                linked_invoice=linked_inv,
                should_confirm=auto_confirm,
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
        refund_ext_id: str,
        order_ext_id: str,
        order_number: str,
        customer_name: str,
        currency: str,
        refund_data: dict[str, Any],
        linked_invoice: AccountingInvoice | None,
        should_confirm: bool,
    ) -> tuple[int, int, int]:
        ref_gross = _to_decimal(
            refund_data.get("amount")
            if refund_data.get("amount") is not None
            else refund_data.get("total_refund") or refund_data.get("total_amount"),
            default=Decimal("0.00"),
        ) or Decimal("0.00")
        if ref_gross <= Decimal("0.00"):
            return 0, 0, 0

        ref_tax = _to_decimal(refund_data.get("tax_amount") or refund_data.get("total_tax"), default=Decimal("0.00")) or Decimal("0.00")
        ref_sub = _to_decimal(refund_data.get("subtotal"), default=None)
        if ref_sub is None:
            ref_sub = max(Decimal("0.00"), (ref_gross - ref_tax).quantize(TWOPLACES, rounding=ROUND_HALF_UP))
        ref_date = _parse_datetime(refund_data.get("created_at"))

        verif_status = "verified_connector" if should_confirm else "to_verify"
        acct_status = "posted" if should_confirm else "proposed"

        c_inv = 0
        c_tx = 0
        skipped = 0

        cn_idem = f"{provider}:{company_id}:{refund_ext_id}:credit_note"
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
                external_id=refund_ext_id,
                idempotency_key=cn_idem,
                verification_status=verif_status,
                accounting_status=acct_status,
                confidence_score=1.0,
                classification_rationale=f"Avoir / remboursement {provider} #{refund_ext_id} sur commande {order_number} (jamais une vente).",
                extra_data={
                    "provider": provider,
                    "order_external_id": order_ext_id,
                    "original_invoice_id": str(linked_invoice.id) if linked_invoice else None,
                },
            )
            self._session.add(cn_inv)
            self._session.flush()
            c_inv += 1
        else:
            skipped += 1

        ref_idem = f"{provider}:{company_id}:{refund_ext_id}:refund"
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
            external_id=refund_ext_id,
            invoice_id=linked_invoice.id if linked_invoice else cn_inv.id,
            extra_data={
                "provider": provider,
                "gross_refund_amount": float(ref_gross),
                "direction": "revenue_reversal",
                "credit_note_id": str(cn_inv.id),
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
        """Réconciliation granulaire entre ventes e-commerce, paiements encaissés, factures et remboursements."""
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

        txs = list(
            self._session.scalars(
                select(AccountingTransaction).where(AccountingTransaction.company_id == company_id)
            ).all()
        )
        invoices = list(
            self._session.scalars(
                select(AccountingInvoice).where(AccountingInvoice.company_id == company_id)
            ).all()
        )

        commerce_gross_sales = Decimal("0.00")
        commerce_taxes = Decimal("0.00")
        commerce_net_sales = Decimal("0.00")
        commerce_refunds_gross = Decimal("0.00")
        commerce_refunds_net = Decimal("0.00")

        inv_by_ext: dict[str, AccountingInvoice] = {
            inv.external_id: inv
            for inv in invoices
            if inv.source_module == "retail" and inv.external_id and inv.invoice_type == "receivable"
        }
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

        for ord_rec in orders:
            data = ord_rec.normalized_data or {}
            ext_id = str(ord_rec.source_record_id)
            gross = _to_decimal(
                data.get("total_price") if data.get("total_price") is not None else data.get("total_amount") or data.get("total"),
                default=Decimal("0.00"),
            ) or Decimal("0.00")
            tax = _to_decimal(data.get("total_tax") or data.get("tax_amount"), default=Decimal("0.00")) or Decimal("0.00")
            sub = _to_decimal(data.get("subtotal_price") or data.get("subtotal"), default=None)
            if sub is None:
                sub = max(Decimal("0.00"), gross - tax)

            commerce_gross_sales += gross
            commerce_taxes += tax
            commerce_net_sales += sub

            for ref in data.get("refunds") or []:
                if isinstance(ref, dict):
                    rg = _to_decimal(ref.get("amount") or ref.get("total_refund"), default=Decimal("0.00")) or Decimal("0.00")
                    rt = _to_decimal(ref.get("tax_amount") or ref.get("total_tax"), default=Decimal("0.00")) or Decimal("0.00")
                    rs = _to_decimal(ref.get("subtotal"), default=None) or max(Decimal("0.00"), rg - rt)
                    commerce_refunds_gross += rg
                    commerce_refunds_net += rs

            linked_inv = inv_by_ext.get(ext_id)
            order_txs = txs_by_ext.get(ext_id, [])
            rev_txs = [t for t in order_txs if t.transaction_type == "revenue"]
            pay_txs = [t for t in order_txs if t.entry_kind == "payment_collected"]

            item_summary = {
                "order_external_id": ext_id,
                "gross_amount": float(gross),
                "net_amount": float(sub),
                "tax_amount": float(tax),
                "invoice_id": str(linked_inv.id) if linked_inv else None,
                "revenue_transaction_ids": [str(t.id) for t in rev_txs],
                "payment_transaction_ids": [str(t.id) for t in pay_txs],
            }
            if linked_inv is None and not rev_txs:
                unlinked_orders.append(item_summary)
            elif any(not t.is_confirmed for t in rev_txs) or (linked_inv is not None and not linked_inv.is_confirmed):
                pending_approval_orders.append(item_summary)
            else:
                matched_orders.append(item_summary)

        for ref_rec in standalone_refunds:
            rdata = ref_rec.normalized_data or {}
            rg = _to_decimal(rdata.get("amount") or rdata.get("total_refund") or rdata.get("total_amount"), default=Decimal("0.00")) or Decimal("0.00")
            rt = _to_decimal(rdata.get("tax_amount") or rdata.get("total_tax"), default=Decimal("0.00")) or Decimal("0.00")
            rs = _to_decimal(rdata.get("subtotal"), default=None) or max(Decimal("0.00"), rg - rt)
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

        acct_net_revenue = (acct_gross_revenue - acct_refunds_net).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        acct_net_tax = (acct_sales_tax - acct_refunds_tax).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        acct_gross_with_tax = (acct_net_revenue + acct_net_tax).quantize(TWOPLACES, rounding=ROUND_HALF_UP)

        expected_commerce_gross_after_refunds = (commerce_gross_sales - commerce_refunds_gross).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        expected_commerce_net_after_refunds = (commerce_net_sales - commerce_refunds_net).quantize(TWOPLACES, rounding=ROUND_HALF_UP)

        discrepancy_gross = float((expected_commerce_gross_after_refunds - acct_gross_with_tax).quantize(TWOPLACES, rounding=ROUND_HALF_UP))
        discrepancy_net = float((expected_commerce_net_after_refunds - acct_net_revenue).quantize(TWOPLACES, rounding=ROUND_HALF_UP))
        is_reconciled = abs(discrepancy_gross) < 0.01 and abs(discrepancy_net) < 0.01

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
