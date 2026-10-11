"""PostgreSQL Row-Level Security helpers.

SQLite tests are a no-op. On PostgreSQL, verified identities bind their company
and disable bypass unless explicitly authorized as platform administrators.
Authentication/internal sessions start with the bypass set in ``get_db``.
Transaction-local settings are restored across commits and rollbacks and never
persist on a pooled connection after the transaction ends.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import event, text
from sqlalchemy.orm import Session


def supports_rls(session: Session) -> bool:
    bind = session.get_bind()
    return bind is not None and bind.dialect.name == "postgresql"


def set_rls_bypass(session: Session, *, enabled: bool) -> None:
    if not supports_rls(session):
        return
    previous = session.info.get("avenqo_rls", {})
    _set_context(session, previous.get("cid", ""), enabled)


def apply_tenant_rls(session: Session, company_id: UUID, *, bypass: bool = False) -> None:
    if not supports_rls(session):
        return
    _set_context(session, str(company_id), bypass)


_CONTEXT_SQL = text(
    "SELECT set_config('app.bypass_rls', :flag, true), "
    "set_config('app.current_company_id', :cid, true)"
)


@event.listens_for(Session, "after_begin")
def _restore_transaction_context(session: Session, transaction, connection) -> None:
    # SET LOCAL expires at commit/rollback. Reapply the authenticated context
    # on each transaction without leaving tenant state on a pooled connection.
    context = session.info.get("avenqo_rls")
    if context is not None and connection.dialect.name == "postgresql":
        connection.execute(_CONTEXT_SQL, context)


def _set_context(session: Session, company_id: str, bypass: bool) -> None:
    context = {"flag": "on" if bypass else "off", "cid": company_id}
    session.info["avenqo_rls"] = context
    if session.in_transaction():
        session.execute(_CONTEXT_SQL, context)
    else:
        session.connection()  # after_begin installs this transaction's context.


TENANT_SCOPED_TABLES = (
    "datasets",
    "commerce_connections",
    "crm_clients",
    "crm_appointments",
    "crm_notes",
    "employee_tasks",
    "employee_responsibilities",
    "employee_invitations",
    "login_events",
    "tenant_documents",
    "media_generations",
    "automation_workflows",
    "automation_runs",
    "audit_log_entries",
)
