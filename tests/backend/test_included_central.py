"""Included Central keeps responding without credit grants or tenant leakage."""
import pytest
from sqlalchemy import select
from backend.app.ai.usage.included_central import included_central, central_is_included
from backend.app.ai.usage.exceptions import AIQuotaExceededError
from backend.app.models import BillingAccount, TenantAIProviderAttempt
from tests.backend.test_central_ai import db_session, make_company, make_service, execute, MeteredStubProvider

@pytest.mark.asyncio
@pytest.mark.parametrize("plan", ["base", "professional", "enterprise"])
async def test_included_central_answers_with_exhausted_balance_and_inactive_plan(db_session, plan):
    company, user = make_company(db_session, plan=plan)
    db_session.add(BillingAccount(company_id=company.id, plan_code=plan, status="inactive"))
    provider = MeteredStubProvider(classification="general")
    central, conversations, usage, tenant = make_service(db_session, company, provider, limit=1, retail_entitled=False)
    balance = usage._get_or_create_credits(company.id)
    balance.monthly_used = 100000
    db_session.commit()
    before = usage.get_credit_balance(company.id, plan)
    conversation = conversations.create(company.id, user.id, "Included Central")
    with included_central(company.id):
        result = await execute(central, tenant, user, conversation, "Bonjour, comment utiliser Avenqo ?")
    assert result.status == "success" and result.answer
    assert provider.calls > 0
    assert usage.get_credit_balance(company.id, plan) == before
    attempts = db_session.scalars(select(TenantAIProviderAttempt)).all()
    assert attempts and all(item.avenqo_credits_charged == 0 for item in attempts)
    assert any(item.provider_cost_usd > 0 for item in attempts)
    assert not central_is_included(company.id)
    with pytest.raises(AIQuotaExceededError):
        usage.ensure_quota_available(company.id, plan)

@pytest.mark.asyncio
async def test_included_scope_never_sponsors_another_tenant(db_session):
    first, _ = make_company(db_session, slug="one")
    second, _ = make_company(db_session, slug="two")
    with included_central(first.id):
        assert central_is_included(first.id)
        assert not central_is_included(second.id)
    assert not central_is_included(first.id)
