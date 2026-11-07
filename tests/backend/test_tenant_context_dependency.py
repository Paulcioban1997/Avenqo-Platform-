from types import SimpleNamespace
from uuid import uuid4

from backend.app.dependencies.auth import CurrentIdentity, get_tenant_context
from shared.ai_engine.contracts import TenantContext


def test_tenant_context_derive_company_from_authenticated_user() -> None:
    company_id = uuid4()
    user_id = uuid4()
    identity = CurrentIdentity(
        auth_session=SimpleNamespace(),
        user=SimpleNamespace(company_id=company_id, id=user_id, is_platform_admin=False),
        raw_token="access-token",
    )
    db = SimpleNamespace(get_bind=lambda: SimpleNamespace(dialect=SimpleNamespace(name="sqlite")))

    tenant = get_tenant_context(identity, db)

    assert isinstance(tenant, TenantContext)
    assert tenant.company_id == company_id
    assert tenant.user_id == user_id
