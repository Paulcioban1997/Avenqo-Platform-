from types import SimpleNamespace
from uuid import uuid4

from backend.app.dependencies.auth import CurrentIdentity, get_tenant_context
from shared.ai_engine.contracts import TenantContext


def test_tenant_context_derive_company_from_authenticated_user() -> None:
    company_id = uuid4()
    identity = CurrentIdentity(
        auth_session=SimpleNamespace(),
        user=SimpleNamespace(company_id=company_id),
        raw_token="access-token",
    )

    tenant = get_tenant_context(identity)

    assert isinstance(tenant, TenantContext)
    assert tenant.company_id == company_id