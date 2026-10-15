from uuid import uuid4

from backend.app.core.tenant_execution import (
    TenantExecutionContext,
    bind_tenant_execution,
    clear_tenant_execution,
    peek_tenant_execution,
    reset_tenant_execution,
)
from shared.ai_engine.contracts import TenantContext


def _context(company_id=None) -> TenantExecutionContext:
    tenant_id = company_id or uuid4()
    user_id = uuid4()
    return TenantExecutionContext(
        tenant=TenantContext(company_id=tenant_id, user_id=user_id),
        user_id=user_id,
        permissions=frozenset({"ai:use"}),
        request_id="reset-test",
        source="test",
    )


def test_bind_reset_does_not_leave_tenant_for_next_caller() -> None:
    first = _context()
    token = bind_tenant_execution(first)
    assert peek_tenant_execution() is first
    reset_tenant_execution(token)
    assert peek_tenant_execution() is None


def test_clear_drops_leftover_bind_from_another_tenant() -> None:
    bind_tenant_execution(_context())
    assert peek_tenant_execution() is not None
    clear_tenant_execution()
    assert peek_tenant_execution() is None
    second = _context()
    bind_tenant_execution(second)
    assert peek_tenant_execution() is second
    clear_tenant_execution()
    assert peek_tenant_execution() is None


def test_sequential_tenants_cannot_see_previous_bind() -> None:
    a = _context()
    b = _context()
    token_a = bind_tenant_execution(a)
    reset_tenant_execution(token_a)
    token_b = bind_tenant_execution(b)
    bound = peek_tenant_execution()
    assert bound is not None
    assert bound.company_id == b.company_id
    assert bound.company_id != a.company_id
    reset_tenant_execution(token_b)
    assert peek_tenant_execution() is None
