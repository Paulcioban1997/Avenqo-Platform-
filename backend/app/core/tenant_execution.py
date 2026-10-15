"""Request-scoped tenant execution context.

`company_id` is taken only from a trusted server identity (JWT session,
validated webhook, or scheduler token). Client headers, query params,
prompt text and LLM tool arguments never bind this context.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from uuid import UUID

from shared.ai_engine.contracts import TenantContext

_UNSET = object()

tenant_execution_var: ContextVar[TenantExecutionContext | None] = ContextVar(
    "avenqo_tenant_execution",
    default=None,
)

CLIENT_TENANT_KEYS = frozenset(
    {
        "company_id",
        "tenant_id",
        "tenant",
        "x_avenqo_tenant_id",
        "avenqo_tenant_id",
        "current_company_id",
        "organization_id",
        "org_id",
    }
)


def _normalized_tenant_keys(key: str) -> frozenset[str]:
    lower = str(key).lower()
    underscored = lower.replace("-", "_")
    return frozenset({lower, underscored, underscored.removeprefix("x_")})


class TenantExecutionError(PermissionError):
    """Raised when tenant context is missing or does not match the bound request."""


@dataclass(frozen=True, slots=True)
class TenantExecutionContext:
    """Trusted execution identity for one request or background job."""

    tenant: TenantContext
    user_id: UUID
    permissions: frozenset[str]
    request_id: str
    rls_bound: bool = True
    rls_bypass: bool = False
    source: str = "session"

    @property
    def company_id(self) -> UUID:
        return self.tenant.company_id

    def matches(self, company_id: UUID) -> bool:
        return self.company_id == company_id


def bind_tenant_execution(context: TenantExecutionContext) -> Token:
    """Bind tenant for the current task/thread. Caller must reset the token."""

    return tenant_execution_var.set(context)


def reset_tenant_execution(token: Token | None) -> None:
    if token is not None:
        tenant_execution_var.reset(token)


def clear_tenant_execution() -> None:
    """Drop any leftover bind. Used after websocket/jobs and between tests."""

    tenant_execution_var.set(None)


def peek_tenant_execution() -> TenantExecutionContext | None:
    return tenant_execution_var.get()


def current_tenant_execution() -> TenantExecutionContext:
    context = tenant_execution_var.get()
    if context is None:
        raise TenantExecutionError("No tenant execution context is bound.")
    return context


def require_same_tenant(company_id: UUID) -> TenantExecutionContext:
    context = current_tenant_execution()
    if not context.matches(company_id):
        raise TenantExecutionError("Requested company is outside the bound tenant.")
    return context


def strip_client_tenant_arguments(raw_arguments: dict[str, object]) -> dict[str, object]:
    """Drop LLM/client tenant selectors before schema validation."""

    return {
        key: value
        for key, value in raw_arguments.items()
        if _normalized_tenant_keys(key).isdisjoint(CLIENT_TENANT_KEYS)
    }


def client_tenant_override(headers=None, query=None, body=None) -> object:
    """Detect a client-supplied tenant selector. Never used as identity."""

    for mapping in (headers, query, body):
        if not mapping:
            continue
        for key, value in mapping.items():
            if _normalized_tenant_keys(key) & CLIENT_TENANT_KEYS and value not in (None, "", _UNSET):
                return value
    return None
