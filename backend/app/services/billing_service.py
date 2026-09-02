"""Cas d'usage de facturation Stripe limités au tenant authentifié."""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.config.settings import Settings
from backend.app.ai.usage.service import AIUsageService
from backend.app.models import BillingAccount, BillingInvoice, Company, StripeWebhookEvent
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
    ) -> None:
        self._session = session
        self._provider = provider
        self._settings = settings
        self._usage_service = usage_service

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
        price_id = self._required_price(plan.code)
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
            self._required_price(plan.code),
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

    def get_credit_balance(self, company_id: UUID, plan_code: str) -> dict[str, Any]:
        return self._usage_service.get_credit_balance(company_id, plan_code)

    def create_credit_checkout(self, company: Company, pack_code: str) -> str:
        account = self.get_account(company.id)
        if account.status not in {"active", "trialing"}:
            raise BillingOperationError("Un abonnement Avenqo actif est requis")
        pack = self._credit_pack(pack_code)
        if pack.plan_code.value != account.plan_code:
            raise BillingOperationError("Pack de crédits indisponible pour cette offre")
        if not account.stripe_customer_id:
            raise BillingOperationError("Client Stripe introuvable pour cet abonnement")
        metadata = {
            "avenqo_kind": "ai_credit_pack",
            "avenqo_company_id": str(company.id),
            "avenqo_credit_pack": pack.code,
            "avenqo_plan_code": account.plan_code,
            "avenqo_credits": str(pack.credits),
        }
        return self._provider.create_credit_checkout(
            account.stripe_customer_id,
            self._required_credit_price(account.plan_code),
            metadata,
            f"{self._settings.frontend_url.rstrip('/')}/billing?credits=success",
            f"{self._settings.frontend_url.rstrip('/')}/billing?credits=cancelled",
        )

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
        if event_type.startswith("customer.subscription."):
            self._sync_subscription(data)
        elif event_type.startswith("invoice."):
            self._sync_invoice(data)
        elif event_type == "checkout.session.completed":
            self._fulfill_credit_checkout(data)
        self._session.add(StripeWebhookEvent(
            stripe_event_id=event_id,
            event_type=event_type,
            processed_at=datetime.now(timezone.utc),
        ))
        self._session.commit()
        return True

    def _fulfill_credit_checkout(self, checkout: dict[str, Any]) -> None:
        metadata = checkout.get("metadata") or {}
        if metadata.get("avenqo_kind") != "ai_credit_pack":
            return
        if checkout.get("payment_status") != "paid":
            raise BillingOperationError("Le paiement du pack de crédits n'est pas confirmé")
        try:
            company_id = UUID(str(metadata["avenqo_company_id"]))
            pack_code = str(metadata["avenqo_credit_pack"])
        except (KeyError, TypeError, ValueError) as exc:
            raise BillingOperationError("Métadonnées du pack de crédits invalides") from exc
        account = self._session.scalar(
            select(BillingAccount).where(BillingAccount.company_id == company_id)
        )
        if account is None or account.status not in {"active", "trialing"}:
            raise BillingOperationError("Abonnement Avenqo inactif pour ce pack de crédits")
        if str(checkout.get("customer") or "") != account.stripe_customer_id:
            raise BillingOperationError("Client Stripe incompatible avec le tenant")
        pack = self._credit_pack(pack_code)
        if metadata.get("avenqo_credits") != str(pack.credits):
            raise BillingOperationError("Quantité du pack de crédits invalide")
        if metadata.get("avenqo_plan_code") != account.plan_code:
            raise BillingOperationError("Offre du pack de crédits incompatible")
        if pack.plan_code.value != account.plan_code:
            raise BillingOperationError("Pack de crédits incompatible avec l'abonnement")
        if not checkout.get("currency") or not isinstance(checkout.get("amount_total"), int):
            raise BillingOperationError("Résultat de paiement Stripe incomplet")
        self._usage_service.add_purchased_credits(company_id, pack.credits)

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
        values = {
            "company_id": company_id,
            "number": invoice.get("number"),
            "plan_code": plan_code,
            "status": str(invoice.get("status") or "unknown"),
            "currency": str(invoice["currency"]),
            "amount_due": int(invoice.get("amount_due", 0)),
            "amount_paid": int(invoice.get("amount_paid", 0)),
            "hosted_invoice_url": invoice.get("hosted_invoice_url"),
            "invoice_pdf": invoice.get("invoice_pdf"),
            "period_start": self._stripe_datetime(period.get("start")),
            "period_end": self._stripe_datetime(period.get("end")),
            "issued_at": issued_at,
        }
        if existing is None:
            self._session.add(BillingInvoice(
                stripe_invoice_id=str(invoice["id"]),
                **values,
            ))
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

    def _required_price(self, plan_code: PlanCode) -> str:
        price_id = self._settings.stripe_price_id(plan_code.value)
        if not price_id:
            raise BillingConfigurationError(f"Prix Stripe non configuré pour {plan_code.value}")
        return price_id

    def _required_credit_price(self, plan_code: str) -> str:
        price_id = self._settings.stripe_credit_price_id(plan_code)
        if not price_id:
            raise BillingConfigurationError(
                f"Prix Stripe du pack de crédits non configuré pour {plan_code}"
            )
        return price_id
