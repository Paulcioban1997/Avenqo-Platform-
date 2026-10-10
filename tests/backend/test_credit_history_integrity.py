from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from sqlalchemy import select
from backend.app.ai.llm.schemas import LLMProviderAttempt, LLMUsage
from backend.app.models import TenantAIProviderAttempt
from backend.app.routers.billing import ai_credits_history
from tests.backend.test_central_ai import db_session, make_company, make_service, StubProvider

def test_credit_history_orders_by_date_and_never_attributes_unknown_actors_to_viewer(db_session):
    company, viewer = make_company(db_session, slug="history")
    foreign_company, foreign_user = make_company(db_session, slug="foreign")
    _, _, usage, _ = make_service(db_session, company, StubProvider(), limit=1, retail_entitled=False)
    now = datetime.now(timezone.utc)
    for index, actor in enumerate([viewer.id, foreign_user.id, None]):
        attempt = LLMProviderAttempt(provider="stub", model="stub", operation="generate", attempt_number=1,
            success=True, latency_ms=1, provider_cost_usd=Decimal("0.001"),
            usage=LLMUsage(provider="stub", model="stub", avenqo_request_id=f"history-{index}", user_id=str(actor) if actor else None))
        usage._record_provider_attempts(company.id, (attempt,), 1)
        db_session.flush()
        record = db_session.scalar(select(TenantAIProviderAttempt).where(TenantAIProviderAttempt.avenqo_request_id == f"history-{index}"))
        record.created_at = now - timedelta(minutes=index)
    db_session.commit()
    result = ai_credits_history(offset=0, limit=10, period="7d", identity=SimpleNamespace(user=viewer), db=db_session)
    assert [item.user for item in result.items] == ["Ari Analyst", "—", "—"]
    assert [item.date for item in result.items] == sorted([item.date for item in result.items], reverse=True)
    assert ai_credits_history(offset=0, limit=10, period="7d", identity=SimpleNamespace(user=foreign_user), db=db_session).total == 0
