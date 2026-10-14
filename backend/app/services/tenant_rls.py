"""PostgreSQL Row-Level Security session helpers.

SQLite tests are a no-op. On PostgreSQL these functions bind
``app.current_company_id`` and ``app.bypass_rls`` for the current transaction.

``get_db`` does not enable bypass. Authenticated tenant routes must call
``apply_tenant_rls`` after the identity is known. Unauthenticated webhooks may
enable bypass only until ``company_id`` is resolved, then must bind the tenant.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


def supports_rls(session: Session) -> bool:
    bind = session.get_bind()
    return bind is not None and bind.dialect.name == "postgresql"


def set_rls_bypass(session: Session, *, enabled: bool) -> None:
    if not supports_rls(session):
        return
    session.execute(
        text("SELECT set_config('app.bypass_rls', :flag, true)"),
        {"flag": "on" if enabled else "off"},
    )


def apply_tenant_rls(session: Session, company_id: UUID, *, bypass: bool = False) -> None:
    if not supports_rls(session):
        return
    session.execute(
        text(
            "SELECT set_config('app.bypass_rls', :flag, true), "
            "set_config('app.current_company_id', :cid, true)"
        ),
        {"flag": "on" if bypass else "off", "cid": str(company_id)},
    )


def bind_webhook_tenant(session: Session, company_id: UUID) -> None:
    """Bind tenant RLS immediately after an unauthenticated webhook resolves company_id."""

    apply_tenant_rls(session, company_id, bypass=False)
