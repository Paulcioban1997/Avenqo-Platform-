"""Sandbox Stripe recovery and pilot contract acceptance. Production gates stay closed."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.config.settings import get_settings
from backend.app.models.base import Base, CompanyStatus, UserRole
from backend.app.models.billing import BillingAccount, BillingInvoice
from backend.app.models.company import Company
from backend.app.models.company_contract import CompanyContract
from backend.app.models.user import User
from backend.app.routers.billing import _stripe_paid_invoice_ids
from backend.app.services.billing_service import BillingService
from backend.app.services.commercial_reconciler import CommercialReconciler
from backend.app.services.contract_signature_service import (
    ContractAuthorityError,
    ContractSignatureService,
)
from backend.app.services.signing_challenge_service import SigningChallengeService
from backend.app.services.stripe_gateway import StripeCustomerNotFoundError


class _Settings:
    def __init__(self, **values):
        self.environment = values.get("environment", "sandbox")
        self.stripe_secret_key = values.get("stripe_secret_key", "sk_test_sandbox")
        self.frontend_url = "https://avenqo-sandbox-web.onrender.com"
        self.provider_incorporation_verified = False
        self.provider_incorporation_status = "UNVERIFIED_PENDING_INCORPORATION"
        self.legal_signing_enabled = False
        self.provider_contracts_published = False
        self.artifact_root = values.get("artifact_root", ".")

    def stripe_price_id(self, plan_code: str, currency: str) -> str:
        return "price_professional_existing"


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'repair.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        yield session


def _company(session) -> Company:
    company = Company(
        name="Produits Ero",
        slug=f"ero-{uuid4().hex[:8]}",
        email=f"ero-{uuid4().hex[:6]}@example.com",
        country="CA",
        timezone="America/Toronto",
        industry="Retail",
        subscription_plan="professional",
        status=CompanyStatus.ACTIVE,
        currency_code="CAD",
    )
    session.add(company)
    session.flush()
    return company


def _owner(session, company: Company) -> User:
    user = User(
        company_id=company.id,
        first_name="Francis",
        last_name="Queval",
        email=f"owner-{uuid4().hex[:6]}@example.com",
        password_hash="hashed",
        role=UserRole.OWNER,
        is_active=True,
        email_verified_at=datetime.now(timezone.utc),
    )
    session.add(user)
    session.commit()
    return user


def test_sandbox_replaces_a_missing_test_customer_and_leaves_old_invoices(db_session):
    company = _company(db_session)
    old_customer = "cus_old_missing"
    account = BillingAccount(
        company_id=company.id,
        plan_code="professional",
        status="active",
        stripe_customer_id=old_customer,
        stripe_subscription_id="sub_old_missing",
    )
    invoice = BillingInvoice(
        company_id=company.id,
        stripe_invoice_id="in_historical_0001",
        stripe_customer_id=old_customer,
        number="XVMNAYLP-0001",
        status="paid",
        currency="usd",
        subtotal=2800,
        total=2800,
        amount_due=0,
        amount_paid=2800,
        line_items=[],
        billing_details={},
        tax_identifiers=[],
        issued_at=datetime.now(timezone.utc),
    )
    db_session.add_all([account, invoice])
    db_session.commit()

    class Provider:
        def get_active_subscription(self, customer_id: str):
            if customer_id == old_customer:
                raise StripeCustomerNotFoundError("missing")
            return None

        def find_customer_by_company(self, company_id: str):
            return None

        def create_customer(self, email: str, name: str, company_id: str) -> str:
            assert company_id == str(company.id)
            return "cus_new_test"

        def create_portal(self, customer_id: str, return_url: str) -> str:
            assert customer_id == "cus_new_test"
            return "https://billing.stripe.com/p/session/test"

        def create_checkout(self, *args, **kwargs):
            raise AssertionError("checkout must wait for the SaaS agreement")

    service = BillingService(db_session, Provider(), _Settings(), None, None)
    url = service.create_portal(company)
    assert url.startswith("https://billing.stripe.com/")
    reloaded = db_session.scalar(select(BillingAccount).where(BillingAccount.company_id == company.id))
    assert reloaded.stripe_customer_id == "cus_new_test"
    assert reloaded.stripe_subscription_id is None
    kept = db_session.scalar(select(BillingInvoice).where(BillingInvoice.number == "XVMNAYLP-0001"))
    assert kept.status == "paid"
    assert kept.amount_paid == 2800
    assert kept.total == 2800

    class Missing:
        def list_customer_invoices(self, customer_id: str, *, limit: int = 100):
            raise StripeCustomerNotFoundError("no such customer")

    confirmed = _stripe_paid_invoice_ids(Missing(), "cus_new_test")
    assert confirmed == set()
    assert "in_historical_0001" not in confirmed


def test_sandbox_reuses_the_tagged_test_customer(db_session):
    company = _company(db_session)
    account = BillingAccount(
        company_id=company.id,
        plan_code="professional",
        status="active",
        stripe_customer_id="cus_old_missing",
        stripe_subscription_id="sub_old_missing",
    )
    db_session.add(account)
    db_session.commit()
    created = {"count": 0}

    class Provider:
        def get_active_subscription(self, customer_id: str):
            if customer_id == "cus_old_missing":
                raise StripeCustomerNotFoundError("missing")
            return None

        def find_customer_by_company(self, company_id: str):
            assert company_id == str(company.id)
            return "cus_existing_test"

        def create_customer(self, *args, **kwargs):
            created["count"] += 1
            raise AssertionError("an existing tagged customer must be reused")

        def create_portal(self, customer_id: str, return_url: str) -> str:
            assert customer_id == "cus_existing_test"
            return "https://billing.stripe.com/p/session/reused"

    service = BillingService(db_session, Provider(), _Settings(), None, None)
    assert service.create_portal(company).endswith("/reused")
    reloaded = db_session.scalar(select(BillingAccount).where(BillingAccount.company_id == company.id))
    assert reloaded.stripe_customer_id == "cus_existing_test"
    assert reloaded.stripe_subscription_id is None
    assert created["count"] == 0


def test_production_does_not_replace_a_missing_customer(db_session):
    company = _company(db_session)
    account = BillingAccount(
        company_id=company.id,
        plan_code="professional",
        status="active",
        stripe_customer_id="cus_keep",
        stripe_subscription_id="sub_keep",
    )
    db_session.add(account)
    db_session.commit()

    class Provider:
        def create_portal(self, customer_id: str, return_url: str) -> str:
            raise StripeCustomerNotFoundError("missing")

        def get_active_subscription(self, customer_id: str):
            return None

        def create_customer(self, *args, **kwargs):
            raise AssertionError("production must not create a replacement customer")

    settings = _Settings(environment="production", stripe_secret_key="sk_live_secret")
    service = BillingService(db_session, Provider(), settings, None, None)
    with pytest.raises(StripeCustomerNotFoundError):
        service.create_portal(company)
    reloaded = db_session.scalar(select(BillingAccount).where(BillingAccount.company_id == company.id))
    assert reloaded.stripe_customer_id == "cus_keep"
    assert reloaded.stripe_subscription_id == "sub_keep"


def test_sandbox_checkout_uses_the_existing_price_after_pilot_saas_acceptance(db_session, tmp_path):
    company = _company(db_session)
    owner = _owner(db_session, company)
    account = BillingAccount(
        company_id=company.id,
        plan_code="professional",
        status="active",
        stripe_customer_id="cus_old_missing",
        stripe_subscription_id="sub_old_missing",
    )
    db_session.add(account)
    db_session.commit()
    settings = get_settings().model_copy(update={
        "environment": "sandbox",
        "stripe_secret_key": None,
        "legal_signing_enabled": False,
        "provider_incorporation_verified": False,
        "provider_contracts_published": False,
        "provider_incorporation_status": "UNVERIFIED_PENDING_INCORPORATION",
        "artifact_root": str(tmp_path),
    })
    contracts = ContractSignatureService(db_session, settings=settings)
    contracts.ensure_contracts_for_company(company)
    saas = contracts.get_contract(company.id, "SAAS_SUBSCRIPTION")
    schedule = CommercialReconciler.reconcile(company, settings)
    challenge, code = SigningChallengeService(db_session).create_challenge(
        company_id=company.id,
        user_id=owner.id,
        contract_id=saas.id,
        contract_version=saas.version,
        content_hash=contracts.compute_sha256(saas.content_text),
        commercial_hash=SigningChallengeService.snapshot_hash(schedule.to_dict()),
    )
    receipt = contracts.sign_contract_electronic(
        company=company,
        user=owner,
        contract_type="SAAS_SUBSCRIPTION",
        signatory_title="Propriétaire",
        declared_authority=True,
        consent_checkbox=True,
        challenge_id=str(challenge.id),
        challenge_code=code,
    )
    assert receipt["signature_mode"] == "SANDBOX_PILOT"
    assert receipt["signature_label"] == "pilot/test"
    signed = contracts.get_contract(company.id, "SAAS_SUBSCRIPTION")
    assert signed.status == "CUSTOMER_SIGNED"
    assert signed.version == "2026-V1"
    assert signed.signatory_email == owner.email
    assert signed.signed_at is not None
    assert signed.provider_signed_at is None
    assert signed.completion_record_json["provider_incorporated"] is False
    assert signed.completion_record_json["provider_countersigned"] is False
    assert signed.completion_record_json["consent_recorded"] is True
    assert contracts.get_contract(company.id, "PRIVATE_LICENSE").status == "PENDING_SIGNATURE"
    assert contracts.sandbox_saas_accepted(company.id) is True
    assert settings.provider_incorporation_verified is False

    production = get_settings().model_copy(update={
        "environment": "production",
        "legal_signing_enabled": False,
        "provider_incorporation_verified": False,
        "provider_contracts_published": False,
        "provider_incorporation_status": "UNVERIFIED_PENDING_INCORPORATION",
    })
    with pytest.raises(ContractAuthorityError):
        ContractSignatureService(db_session, settings=production).sign_contract_electronic(
            company=company, user=owner, contract_type="MUTUAL_NDA",
            signatory_title="Propriétaire", declared_authority=True, consent_checkbox=True,
        )

    class Provider:
        def get_active_subscription(self, customer_id: str):
            if customer_id == "cus_old_missing":
                raise StripeCustomerNotFoundError("missing")
            return None

        def find_customer_by_company(self, company_id: str):
            return None

        def create_customer(self, email: str, name: str, company_id: str) -> str:
            return "cus_checkout_test"

        def create_checkout(self, customer_id, price_id, company_id, success_url, cancel_url, *, idempotency_key=None):
            assert customer_id == "cus_checkout_test"
            assert price_id == "price_professional_existing"
            assert "checkout=success" in success_url
            assert "checkout=cancelled" in cancel_url
            assert idempotency_key
            return "https://checkout.stripe.com/c/pay/cs_test_session"

        def create_portal(self, customer_id: str, return_url: str) -> str:
            raise AssertionError("an accepted SaaS agreement should open Checkout")

    billing = BillingService(db_session, Provider(), _Settings(), None, None)
    assert billing.create_portal(company) == "https://checkout.stripe.com/c/pay/cs_test_session"
