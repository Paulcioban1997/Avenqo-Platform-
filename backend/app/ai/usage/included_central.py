"""Server-only, request-scoped sponsorship of the included Central AI assistant."""
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import UUID

_included_tenant: ContextVar[UUID | None] = ContextVar("included_central_tenant", default=None)


def central_is_included(company_id: UUID) -> bool:
    return _included_tenant.get() == company_id


@contextmanager
def included_central(company_id: UUID):
    token = _included_tenant.set(company_id)
    try:
        yield
    finally:
        _included_tenant.reset(token)
