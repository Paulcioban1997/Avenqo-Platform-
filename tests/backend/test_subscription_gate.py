import pytest
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.dependencies.subscription import require_active_subscription
from backend.app.models import Base, BillingAccount, Company
from backend.app.models.base import UserRole
from backend.app.models.user import User
from backend.app.services.contract_signature_service import ContractSignatureService
from shared.ai_engine.contracts import TenantContext


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'subscription-gate.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        yield session


def _tenant(db_session, *, plan: str, subscription_status: str, sign_contracts: bool = True):
    suffix = str(len(db_session.identity_map))
    company = Company(
        name=f"{plan}-{subscription_status}",
        slug=f"{plan}-{subscription_status}-{suffix}",
        email=f"{plan}-{subscription_status}-{suffix}@example.com",
        country="CA",
        timezone="America/Toronto",
        industry="Retail",
        subscription_plan=plan,
    )
    db_session.add(company)
    db_session.flush()
    db_session.add(
        BillingAccount(
            company_id=company.id,
            plan_code=plan,
            status=subscription_status,
        )
    )
    db_session.flush()

    if sign_contracts and subscription_status in ("active", "trialing"):
        user = User(
            id=uuid4(),
            company_id=company.id,
            email=f"owner-{suffix}@example.com",
            first_name="Admin",
            last_name="Test",
            password_hash="pw",
            role=UserRole.OWNER,
        )
        db_session.add(user)
        db_session.flush()
        service = ContractSignatureService(db_session)
        service.ensure_contracts_for_company(company)
        service.sign_contract_electronic(
            company=company,
            user=user,
            contract_type="MUTUAL_NDA",
            signatory_title="CEO",
            declared_authority=True,
            consent_checkbox=True,
        )
        service.sign_contract_electronic(
            company=company,
            user=user,
            contract_type="SAAS_SUBSCRIPTION",
            signatory_title="CEO",
            declared_authority=True,
            consent_checkbox=True,
        )

    db_session.commit()
    return TenantContext(company_id=company.id)


@pytest.mark.parametrize(
    ("plan", "subscription_status"),
    [("demo", "active"), ("professional", "active"), ("demo", "trialing")],
)
def test_active_and_trialing_tenants_are_allowed(db_session, plan, subscription_status) -> None:
    tenant = _tenant(db_session, plan=plan, subscription_status=subscription_status)

    assert require_active_subscription(tenant, db_session) is tenant


@pytest.mark.parametrize(
    "subscription_status",
    [
        "inactive",
        "canceled",
        "incomplete",
        "incomplete_expired",
        "expired",
        "unpaid",
        "past_due",
    ],
)
def test_non_active_subscriptions_are_blocked_consistently(db_session, subscription_status) -> None:
    tenant = _tenant(db_session, plan="demo", subscription_status=subscription_status)

    with pytest.raises(HTTPException) as exc_info:
        require_active_subscription(tenant, db_session)

    assert exc_info.value.status_code == 402
    assert exc_info.value.detail == "Un abonnement actif est requis"
