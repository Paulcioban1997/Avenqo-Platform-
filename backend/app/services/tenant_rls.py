"""PostgreSQL Row-Level Security helpers.

SQLite tests are a no-op. On PostgreSQL, tenant routes disable the session bypass
and bind ``app.current_company_id``. Administrative, internal and migration
sessions keep ``app.bypass_rls=on`` (the default set in ``get_db``).
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
        text("SELECT set_config('app.bypass_rls', :flag, true), set_config('app.current_company_id', :cid, true)"),
        {"flag": "on" if bypass else "off", "cid": str(company_id)},
    )


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
