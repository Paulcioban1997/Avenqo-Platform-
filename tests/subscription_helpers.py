"""Helpers for test tenants that exercise subscription-protected APIs."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import BillingAccount, Company


def add_active_subscription(session: Session, company: Company) -> None:
    session.add(
        BillingAccount(
            company_id=company.id,
            plan_code=company.subscription_plan,
            status="active",
        )
    )


def activate_subscription(session: Session, company: Company) -> None:
    account = session.scalar(
        select(BillingAccount).where(BillingAccount.company_id == company.id)
    )
    if account is None:
        add_active_subscription(session, company)
    else:
        account.plan_code = company.subscription_plan
        account.status = "active"
    session.commit()


def activate_subscription_by_id(session: Session, company_id: UUID | str) -> None:
    company = session.get(Company, UUID(str(company_id)))
    if company is None:
        raise AssertionError(f"Test company {company_id} does not exist")
    activate_subscription(session, company)