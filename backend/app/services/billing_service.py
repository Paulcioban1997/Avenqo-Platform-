"""Cas d'usage de facturation Stripe limités au tenant authentifié."""

from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.config.settings import Settings
from backend.app.ai.usage.service import AIUsageService
from backend.app.models import (
    AICreditPurchase,
    BillingAccount,
    BillingInvoice,
    Company,
    StripeWebhookEvent,
    User,
    UserRole,
)
from backend.app.services.account_notifications import AccountNotifier
from backend.app.services.stripe_gateway import BillingProvider
from payments import PlanCode, get_plan
from payments.plans import AI_CREDIT_PACKS, AICreditPack, get_ai_credit_pack


class BillingConfigurationError(RuntimeError):
    pass


class BillingOperationError(ValueError):
    pass


class BillingService:
    """Orchestre Stripe sans transmettre de logique de paiement aux modules IA."""

    def __init__(
        self,
        session: Session,
        provider: BillingProvider,
        settings: Settings,
        usage_service: AIUsageService,
        notifier: AccountNotifier,
    ) -> None:
        self._session = session
        self._provider = provider
        self._settings = settings
        self._usage_service = usage_service
        self._notifier = notifier

    def get_account(self, company_id: UUID) -> BillingAccount:
        account = self._session.scalar(select(BillingAccount).where(
            BillingAccount.company_id == company_id,
        ))
        if account is None:
            account = BillingAccount(company_id=company_id, plan_code="demo", status="inactive")
            self._session.add(account)
            self._session.flush()
        return account

    def create_checkout(self, company: Company, plan_code: str) -> str:
        plan = get_plan(plan_code)
        if plan.requires_sales_contact:
            raise BillingOperationError(f"{plan.name} nécessite un contact commercial")
        price_id = self._required_price(plan.code, company.currency_code)
        account = self.get_account(company.id)
        if account.stripe_subscription_id and account.status not in {"canceled", "incomplete_expired"}:
            raise BillingOperationError("Un abonnement existe déjà; utilisez le changement d'offre")
        if not account.stripe_customer_id:
            account.stripe_customer_id = self._provider.create_customer(
                company.email,
                company.name,
                str(company.id),
            )
            self._session.commit()
        return self._provider.create_checkout(
            account.stripe_customer_id,
            price_id,
            str(company.id),
            f"{self._settings.frontend_url.rstrip('/')}/billing?checkout=success",
            f"{self._settings.frontend_url.rstrip('/')}/pricing?checkout=cancelled",
        )

    def change_plan(self, company_id: UUID, plan_code: str) -> BillingAccount:
        plan = get_plan(plan_code)
        if plan.requires_sales_contact:
            raise BillingOperationError(f"{plan.name} nécessite un contact commercial")
        account = self.get_account(company_id)
        if not account.stripe_subscription_id:
            raise BillingOperationError("Aucun abonnement Stripe actif")
        self._provider.change_subscription(
            account.stripe_subscription_id,
            self._required_price(plan.code, account.company.currency_code),
        )
        return account

    def cancel(self, company_id: UUID) -> BillingAccount:
        account = self.get_account(company_id)
        if not account.stripe_subscription_id:
            raise BillingOperationError("Aucun abonnement Stripe actif")
        self._provider.cancel_subscription(account.stripe_subscription_id)
        account.cancel_at_period_end = True
        self._session.commit()
        return account

    def create_portal(self, company: Company) -> str:
        """Ouvre le portail Stripe et crée le Customer à la demande si nécessaire."""
        account = self.get_account(company.id)
        if not account.stripe_customer_id:
            account.stripe_customer_id = self._provider.create_customer(
                company.email,
                company.name,
                str(company.id),
            )
            self._session.commit()
        return self._provider.create_portal(
            account.stripe_customer_id,
            f"{self._settings.frontend_url.rstrip('/')}/billing",
        )

    def list_invoices(self, company_id: UUID) -> list[BillingInvoice]:
        return list(self._session.scalars(
            select(BillingInvoice)
            .where(BillingInvoice.company_id == company_id)
            .order_by(BillingInvoice.issued_at.desc())
        ))

    def list_credit_packs(
        self,
        company_id: UUID,
        fallback_plan_code: str,
    ) -> list[dict[str, Any]]:
        account = self._session.scalar(
            select(BillingAccount).where(BillingAccount.company_id == company_id)
        )
        plan_code = account.plan_code if account is not None else fallback_plan_code
        return [
            {"code": pack.code, "credits": pack.credits, "price_usd": pack.price_usd}
            for pack in AI_CREDIT_PACKS
            if pack.plan_code.value == plan_code
        ]

    def get_credit_balance(self, company_id: UUID, fallback_plan_code: str) -> dict[str, Any]:
        account = self._session.scalar(
            select(BillingAccount).where(BillingAccount.company_id == company_id)
        )
        plan_code = account.plan_code if account is not None else fallback_plan_code
        balance = self._usage_service.get_credit_balance(company_id, plan_code)
        period_start = datetime.strptime(
            str(balance["billing_period"]),
            "%Y-%m",
        ).replace(tzinfo=timezone.utc)
        period_end = period_start.replace(
            year=period_start.year + (period_start.month == 12),
            month=1 if period_start.month == 12 else period_start.month + 1,
        )
        return {
            **balance,
            "billing_period_start": period_start,
            "billing_period_end": period_end,
            "monthly_allocation": balance["monthly_included"],
            "purchased_total_available": balance["purchased_remaining"],
            "total_available": balance["total_remaining"],
        }

    def create_credit_checkout(self, company: Company, pack_code: str) -> str:
        account = self.get_account(company.id)
        if account.status not in {"active", "trialing"}:
            raise BillingOperationError("Un abonnement Avenqo actif est requis")
        pack = self._credit_pack(pack_code)
        if pack.plan_code.value != account.plan_code:
            raise BillingOperationError("Pack de crédits indisponible pour cette offre")
        if not account.stripe_customer_id:
            raise BillingOperationError("Client Stripe introuvable pour cet abonnement")
        purchase = AICreditPurchase(
            id=uuid4(),
            company_id=company.id,
            stripe_customer_id=account.stripe_customer_id,
            pack_code=pack.code,
            plan_code=account.plan_code,
            price_usd_cents=pack.price_usd * 100,
            status="creating",
        )
        self._session.add(purchase)
        self._session.commit()
        metadata = {
            "avenqo_kind": "ai_credit_pack",
            "avenqo_company_id": str(company.id),
            "avenqo_credit_purchase_id": str(purchase.id),
            "avenqo_credit_pack": pack.code,
            "avenqo_plan_code": account.plan_code,
            "avenqo_credits": str(pack.credits),
        }
        try:
            checkout = self._provider.create_credit_checkout(
                account.stripe_customer_id,
                self._required_credit_price(pack.code),
                metadata,
                f"{self._settings.frontend_url.rstrip('/')}/billing?credits=success",
                f"{self._settings.frontend_url.rstrip('/')}/billing?credits=cancelled",
            )
        except Exception:
            purchase.status = "checkout_failed"
            self._session.commit()
            raise
        purchase.stripe_checkout_session_id = checkout.id
        if purchase.status == "creating":
            purchase.status = "pending"
        self._session.commit()
        return checkout.url

    def process_webhook(self, payload: bytes, signature: str) -> bool:
        if not self._settings.stripe_webhook_secret:
            raise BillingConfigurationError("STRIPE_WEBHOOK_SECRET n'est pas configuré")
        event = self._provider.construct_event(
            payload,
            signature,
            self._settings.stripe_webhook_secret,
        )
        event_id = str(event["id"])
        if self._session.get(StripeWebhookEvent, event_id):
            return False

        event_type = str(event["type"])
        data = event["data"]["object"]
        if hasattr(data, "to_dict_recursive"):
            data = data.to_dict_recursive()
        elif hasattr(data, "to_dict"):
            data = data.to_dict()
        if event_type.startswith("customer.subscription."):
            self._sync_subscription(data)
        elif event_type.startswith("invoice."):
            self._sync_invoice(data)
        elif event_type in {
            "checkout.session.completed",
            "checkout.session.async_payment_succeeded",
        }:
            self._fulfill_credit_checkout(
                data,
                payment_confirmed=event_type == "checkout.session.async_payment_succeeded",
            )
        elif event_type == "checkout.session.async_payment_failed":
            self._mark_credit_checkout_failed(data)
        elif event_type == "charge.refunded":
            self._refund_credit_purchase(data)
        self._session.add(StripeWebhookEvent(
            stripe_event_id=event_id,
            event_type=event_type,
            processed_at=datetime.now(timezone.utc),
        ))
        self._session.commit()
        return True

    def _fulfill_credit_checkout(
        self,
        checkout: dict[str, Any],
        *,
        payment_confirmed: bool = False,
    ) -> None:
        resolved = self._resolve_credit_purchase(checkout)
        if resolved is None:
            return
        purchase, pack = resolved
        if not payment_confirmed and checkout.get("payment_status") != "paid":
            if purchase.status in {"creating", "pending"}:
                purchase.status = "pending_payment"
            return
        if purchase.credits_granted > 0 or purchase.status == "refunded":
            return
        credits_to_grant = max(pack.credits - purchase.credits_reversed, 0)
        if credits_to_grant:
            self._usage_service.add_purchased_credits(
                purchase.company_id,
                credits_to_grant,
                idempotency_key=f"credit-purchase:{purchase.id}",
                reference_id=str(purchase.id),
                details={
                    "pack_code": purchase.pack_code,
                    "stripe_checkout_session_id": purchase.stripe_checkout_session_id,
                    "stripe_payment_intent_id": purchase.stripe_payment_intent_id,
                },
            )
            purchase.credits_granted = credits_to_grant
            purchase.credits_remaining = credits_to_grant
        purchase.status = "partially_refunded" if purchase.refunded_amount else "paid"

    def _resolve_credit_purchase(
        self,
        checkout: dict[str, Any],
    ) -> tuple[AICreditPurchase, AICreditPack] | None:
        metadata = checkout.get("metadata") or {}
        if metadata.get("avenqo_kind") != "ai_credit_pack":
            return None
        try:
            company_id = UUID(str(metadata["avenqo_company_id"]))
            pack_code = str(metadata["avenqo_credit_pack"])
        except (KeyError, TypeError, ValueError) as exc:
            raise BillingOperationError("Métadonnées du pack de crédits invalides") from exc
        account = self._session.scalar(
            select(BillingAccount).where(BillingAccount.company_id == company_id)
        )
        if account is None:
            raise BillingOperationError("Compte de facturation introuvable pour ce pack de crédits")
        if str(checkout.get("customer") or "") != account.stripe_customer_id:
            raise BillingOperationError("Client Stripe incompatible avec le tenant")
        pack = self._credit_pack(pack_code)
        if metadata.get("avenqo_credits") != str(pack.credits):
            raise BillingOperationError("Quantité du pack de crédits invalide")
        checkout_session_id = str(checkout.get("id") or "")
        payment_intent_id = str(checkout.get("payment_intent") or "")
        if not checkout_session_id:
            raise BillingOperationError("Session Checkout Stripe absente")
        if not payment_intent_id:
            raise BillingOperationError("PaymentIntent Stripe absent")
        amount_total = checkout.get("amount_total")
        currency = str(checkout.get("currency") or "").lower()
        if not currency or not isinstance(amount_total, int) or amount_total < 0:
            raise BillingOperationError("Résultat de paiement Stripe incomplet")

        purchase_id = metadata.get("avenqo_credit_purchase_id")
        purchase = None
        if purchase_id:
            try:
                purchase = self._session.get(AICreditPurchase, UUID(str(purchase_id)))
            except ValueError as exc:
                raise BillingOperationError("Référence d'achat de crédits invalide") from exc
            if purchase is None:
                raise BillingOperationError("Achat de crédits introuvable")
        by_session = self._session.scalar(select(AICreditPurchase).where(
            AICreditPurchase.stripe_checkout_session_id == checkout_session_id
        ))
        by_payment = self._session.scalar(select(AICreditPurchase).where(
            AICreditPurchase.stripe_payment_intent_id == payment_intent_id
        ))
        matched = {item.id for item in (purchase, by_session, by_payment) if item is not None}
        if len(matched) > 1:
            raise BillingOperationError("Références Stripe associées à des achats différents")
        purchase = purchase or by_session or by_payment
        if purchase is None:
            if account.status not in {"active", "trialing"}:
                raise BillingOperationError("Abonnement Avenqo inactif pour ce pack de crédits")
            if metadata.get("avenqo_plan_code") != account.plan_code:
                raise BillingOperationError("Offre du pack de crédits incompatible")
            if pack.plan_code.value != account.plan_code:
                raise BillingOperationError("Pack de crédits incompatible avec l'abonnement")
            purchase = AICreditPurchase(
                company_id=company_id,
                stripe_customer_id=account.stripe_customer_id,
                stripe_checkout_session_id=checkout_session_id,
                stripe_payment_intent_id=payment_intent_id,
                pack_code=pack.code,
                plan_code=pack.plan_code.value,
                price_usd_cents=pack.price_usd * 100,
                status="pending",
            )
            self._session.add(purchase)
            self._session.flush()

        if purchase.company_id != company_id or purchase.stripe_customer_id != account.stripe_customer_id:
            raise BillingOperationError("Achat de crédits incompatible avec le tenant")
        if purchase.pack_code != pack.code or purchase.plan_code != str(metadata.get("avenqo_plan_code")):
            raise BillingOperationError("Métadonnées incompatibles avec l'achat de crédits")
        if purchase.stripe_checkout_session_id not in {None, checkout_session_id} and by_payment is None:
            raise BillingOperationError("Session Checkout incompatible avec l'achat de crédits")
        if purchase.stripe_payment_intent_id not in {None, payment_intent_id}:
            raise BillingOperationError("PaymentIntent incompatible avec l'achat de crédits")
        purchase.stripe_checkout_session_id = purchase.stripe_checkout_session_id or checkout_session_id
        purchase.stripe_payment_intent_id = purchase.stripe_payment_intent_id or payment_intent_id
        purchase.amount_paid = amount_total
        purchase.currency = currency
        return purchase, pack

    def _mark_credit_checkout_failed(self, checkout: dict[str, Any]) -> None:
        resolved = self._resolve_credit_purchase(checkout)
        if resolved is None:
            return
        purchase, _ = resolved
        if purchase.credits_granted == 0 and purchase.status != "refunded":
            purchase.status = "failed"

    def _refund_credit_purchase(self, charge: dict[str, Any]) -> None:
        payment_intent_id = str(charge.get("payment_intent") or "")
        metadata = charge.get("metadata") or {}
        purchase = self._session.scalar(select(AICreditPurchase).where(
            AICreditPurchase.stripe_payment_intent_id == payment_intent_id
        )) if payment_intent_id else None
        if purchase is None and metadata.get("avenqo_credit_purchase_id"):
            try:
                purchase = self._session.get(
                    AICreditPurchase,
                    UUID(str(metadata["avenqo_credit_purchase_id"])),
                )
            except ValueError as exc:
                raise BillingOperationError("Référence de remboursement invalide") from exc
        if purchase is None:
            raise BillingOperationError("Achat de crédits introuvable pour le remboursement")
        if payment_intent_id:
            if purchase.stripe_payment_intent_id not in {None, payment_intent_id}:
                raise BillingOperationError("PaymentIntent incompatible avec le remboursement")
            purchase.stripe_payment_intent_id = payment_intent_id
        charge_customer = str(charge.get("customer") or "")
        if charge_customer and charge_customer != purchase.stripe_customer_id:
            raise BillingOperationError("Client Stripe incompatible avec le remboursement")

        amount_paid = purchase.amount_paid or int(charge.get("amount") or 0)
        refunded_amount = int(charge.get("amount_refunded") or 0)
        if amount_paid <= 0 or refunded_amount < 0 or refunded_amount > amount_paid:
            raise BillingOperationError("Montant de remboursement Stripe invalide")
        currency = str(charge.get("currency") or purchase.currency or "").lower()
        if not currency or (purchase.currency and purchase.currency != currency):
            raise BillingOperationError("Devise de remboursement Stripe incompatible")
        purchase.amount_paid = amount_paid
        purchase.currency = currency

        pack = self._credit_pack(purchase.pack_code)
        target_reversal = int(
            (Decimal(pack.credits) * Decimal(refunded_amount) / Decimal(amount_paid)).to_integral_value(
                rounding=ROUND_CEILING
            )
        )
        handled_reversal = purchase.credits_reversed + purchase.refund_shortfall_credits
        incremental_reversal = max(target_reversal - handled_reversal, 0)
        if incremental_reversal and purchase.credits_granted == 0:
            purchase.credits_reversed += incremental_reversal
            self._usage_service.record_credit_event(
                purchase.company_id,
                idempotency_key=f"credit-refund:{purchase.id}:{refunded_amount}",
                transaction_type="purchase_refund_withheld",
                reference_id=str(purchase.id),
                details={"credits": incremental_reversal, "amount_refunded": refunded_amount},
            )
        elif incremental_reversal:
            reversible = min(
                incremental_reversal,
                max(purchase.credits_remaining - purchase.credits_reserved, 0),
            )
            reversed_credits = self._usage_service.reverse_purchased_credits(
                purchase.company_id,
                reversible,
                idempotency_key=f"credit-refund:{purchase.id}:{refunded_amount}",
                reference_id=str(purchase.id),
                details={"credits_requested": incremental_reversal, "amount_refunded": refunded_amount},
            )
            purchase.credits_remaining -= reversed_credits
            purchase.credits_reversed += reversed_credits
            purchase.refund_shortfall_credits += incremental_reversal - reversed_credits
        purchase.refunded_amount = max(purchase.refunded_amount, refunded_amount)
        purchase.review_required = purchase.refund_shortfall_credits > 0
        if purchase.review_required:
            purchase.status = "refund_review"
        elif purchase.refunded_amount == amount_paid:
            purchase.status = "refunded"
        else:
            purchase.status = "partially_refunded"

    @staticmethod
    def _credit_pack(code: str) -> AICreditPack:
        try:
            return get_ai_credit_pack(code)
        except ValueError as exc:
            raise BillingOperationError("Pack de crédits inconnu") from exc

    def _sync_subscription(self, subscription: dict[str, Any]) -> None:
        company_id = self._company_id(subscription)
        account = self.get_account(company_id)
        price_id = str(subscription["items"]["data"][0]["price"]["id"])
        plan_code = self._settings.stripe_plan_code(price_id)
        if plan_code is None:
            raise BillingConfigurationError(f"Prix Stripe inconnu: {price_id}")
        account.stripe_customer_id = str(subscription["customer"])
        account.stripe_subscription_id = str(subscription["id"])
        account.plan_code = plan_code
        account.status = str(subscription["status"])
        account.cancel_at_period_end = bool(subscription.get("cancel_at_period_end", False))
        period_end = subscription.get("current_period_end")
        account.current_period_end = (
            datetime.fromtimestamp(int(period_end), timezone.utc) if period_end else None
        )
        account.company.subscription_plan = plan_code

    def _sync_invoice(self, invoice: dict[str, Any]) -> None:
        company_id = self._invoice_company_id(invoice)
        account = self.get_account(company_id)
        existing = self._session.scalar(select(BillingInvoice).where(
            BillingInvoice.stripe_invoice_id == str(invoice["id"]),
        ))
        issued_at = datetime.fromtimestamp(int(invoice["created"]), timezone.utc)
        lines = (invoice.get("lines") or {}).get("data") or []
        line = lines[0] if lines else {}
        period = line.get("period") or {}
        price_id = str((line.get("price") or {}).get("id") or "")
        plan_code = self._settings.stripe_plan_code(price_id) or account.plan_code
        parent = invoice.get("parent") or {}
        subscription_details = parent.get("subscription_details") or {}
        subscription_id = (
            subscription_details.get("subscription")
            or invoice.get("subscription")
            or account.stripe_subscription_id
        )
        discounts = invoice.get("total_discount_amounts") or []
        taxes = invoice.get("total_tax_amounts") or []
        status_transitions = invoice.get("status_transitions") or {}
        values = {
            "company_id": company_id,
            "stripe_subscription_id": str(subscription_id) if subscription_id else None,
            "stripe_customer_id": str(invoice.get("customer") or "") or None,
            "number": invoice.get("number"),
            "plan_code": plan_code,
            "status": str(invoice.get("status") or "unknown"),
            "currency": str(invoice["currency"]),
            "subtotal": int(invoice.get("subtotal", 0)),
            "discount_total": sum(int(item.get("amount", 0)) for item in discounts),
            "tax_total": sum(int(item.get("amount", 0)) for item in taxes),
            "total": int(invoice.get("total", invoice.get("amount_due", 0))),
            "amount_due": int(invoice.get("amount_due", 0)),
            "amount_paid": int(invoice.get("amount_paid", 0)),
            "line_items": [self._line_item_snapshot(item) for item in lines],
            "billing_details": {
                "name": invoice.get("customer_name"),
                "address": invoice.get("customer_address"),
                "phone": invoice.get("customer_phone"),
            },
            "tax_identifiers": invoice.get("customer_tax_ids") or [],
            "customer_email": invoice.get("customer_email"),
            "hosted_invoice_url": invoice.get("hosted_invoice_url"),
            "invoice_pdf": invoice.get("invoice_pdf"),
            "period_start": self._stripe_datetime(period.get("start")),
            "period_end": self._stripe_datetime(period.get("end")),
            "issued_at": issued_at,
            "paid_at": self._stripe_datetime(status_transitions.get("paid_at")),
            "due_at": self._stripe_datetime(invoice.get("due_date")),
        }
        if existing is None:
            existing = BillingInvoice(
                stripe_invoice_id=str(invoice["id"]),
                **values,
            )
            self._session.add(existing)
        else:
            for field, value in values.items():
                setattr(existing, field, value)
        if (
            invoice.get("status") == "paid"
            and invoice.get("billing_reason") == "subscription_cycle"
        ):
            period_start = values["period_start"] or issued_at
            self._usage_service.reset_credits_for_renewal(
                company_id,
                period_start.strftime("%Y-%m"),
            )
        if invoice.get("status") == "paid" and existing.email_sent_at is None:
            recipient = self._invoice_recipient(account.company, values["customer_email"])
            if recipient and getattr(self._notifier, "email_delivery_configured", True):
                self._notifier.send_invoice_paid(recipient, account.company, existing)
                existing.email_sent_at = datetime.now(timezone.utc)

    @staticmethod
    def _line_item_snapshot(line: dict[str, Any]) -> dict[str, Any]:
        price = line.get("price") or {}
        return {
            "description": line.get("description"),
            "quantity": line.get("quantity"),
            "amount": int(line.get("amount", 0)),
            "currency": line.get("currency"),
            "price_id": price.get("id"),
            "product_id": price.get("product"),
        }

    def _invoice_recipient(self, company: Company, stripe_email: object) -> str | None:
        if company.billing_email.strip():
            return company.billing_email.strip().lower()
        if stripe_email:
            return str(stripe_email).strip().lower()
        owner = self._session.scalar(
            select(User)
            .where(
                User.company_id == company.id,
                User.role.in_((UserRole.OWNER, UserRole.ADMIN)),
            )
            .order_by(User.role.asc())
        )
        return owner.email if owner else None

    @staticmethod
    def _stripe_datetime(timestamp: object) -> datetime | None:
        return datetime.fromtimestamp(int(timestamp), timezone.utc) if timestamp else None

    def _invoice_company_id(self, invoice: dict[str, Any]) -> UUID:
        parent = invoice.get("parent") or {}
        subscription_details = parent.get("subscription_details") or {}
        metadata = subscription_details.get("metadata") or invoice.get("metadata") or {}
        raw_company_id = metadata.get("avenqo_company_id")
        if raw_company_id:
            return UUID(str(raw_company_id))
        customer_id = str(invoice["customer"])
        account = self._session.scalar(select(BillingAccount).where(
            BillingAccount.stripe_customer_id == customer_id,
        ))
        if account is None:
            raise BillingOperationError("Tenant introuvable pour la facture Stripe")
        return account.company_id

    @staticmethod
    def _company_id(resource: dict[str, Any]) -> UUID:
        raw_company_id = (resource.get("metadata") or {}).get("avenqo_company_id")
        if not raw_company_id:
            raise BillingOperationError("Métadonnée avenqo_company_id absente")
        return UUID(str(raw_company_id))

    def _required_price(self, plan_code: PlanCode, currency_code: str) -> str:
        price_id = self._settings.stripe_price_id(plan_code.value, currency_code)
        if not price_id:
            raise BillingConfigurationError(
                f"Prix Stripe non configuré pour {plan_code.value} en {currency_code}"
            )
        return price_id

    def _required_credit_price(self, pack_code: str) -> str:
        price_id = self._settings.stripe_credit_price_id(pack_code)
        if not price_id:
            raise BillingConfigurationError(
                f"Prix Stripe du pack de crédits non configuré pour {pack_code}"
            )
        return price_id
