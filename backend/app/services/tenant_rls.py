"""PostgreSQL Row-Level Security session helpers.

SQLite tests are a no-op. On PostgreSQL these functions bind
``app.current_company_id`` and ``app.bypass_rls`` for the current transaction.

``get_db`` does not enable bypass. Authenticated tenant routes must call
``apply_tenant_rls`` after the identity is known. Unauthenticated webhooks may
enable bypass only until ``company_id`` is resolved, then must bind the tenant.

Transaction-local settings are restored across commits and rollbacks and never
persist on a pooled connection after the transaction ends.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import event, inspect, text
from sqlalchemy.orm import Session


def supports_rls(session: Session) -> bool:
    getter = getattr(session, "get_bind", None)
    if not callable(getter):
        return False
    try:
        bind = getter()
    except Exception:
        return False
    dialect = getattr(bind, "dialect", None)
    return dialect is not None and getattr(dialect, "name", None) == "postgresql"


def set_rls_bypass(session: Session, *, enabled: bool) -> None:
    if not supports_rls(session):
        return
    info = getattr(session, "info", None)
    previous = info.get("avenqo_rls", {}) if isinstance(info, dict) else {}
    _set_context(session, previous.get("cid", ""), enabled)


def apply_tenant_rls(session: Session, company_id: UUID, *, bypass: bool = False) -> None:
    if not supports_rls(session):
        return
    _set_context(session, str(company_id), bypass)


def bind_webhook_tenant(session: Session, company_id: UUID) -> None:
    """Bind tenant RLS immediately after an unauthenticated webhook resolves company_id."""

    apply_tenant_rls(session, company_id, bypass=False)


def release_tenant_connection(session: object | None) -> None:
    """Persist pending SQL and return the pooled connection before a network await.

    ``session.info['avenqo_rls']`` is kept so the next autobegin re-applies
    SET LOCAL. Fake/test sessions without commit/close are ignored.
    """

    if session is None:
        return
    info = getattr(session, "info", None)
    rls = dict(info.get("avenqo_rls") or {}) if isinstance(info, dict) else {}
    commit = getattr(session, "commit", None)
    rollback = getattr(session, "rollback", None)
    close = getattr(session, "close", None)
    try:
        if callable(commit):
            commit()
    except Exception:
        if callable(rollback):
            try:
                rollback()
            except Exception:
                pass
    if callable(close):
        close()
    restored = getattr(session, "info", None)
    if rls and isinstance(restored, dict):
        restored["avenqo_rls"] = rls


_CONTEXT_SQL = text(
    "SELECT set_config('app.current_company_id', :cid, true), "
    "set_config('app.bypass_rls', :flag, true)"
)


@event.listens_for(Session, "after_begin")
def _restore_transaction_context(session: Session, transaction, connection) -> None:
    # SET LOCAL expires at commit/rollback. Reapply the authenticated context
    # on each transaction without leaving tenant state on a pooled connection.
    context = session.info.get("avenqo_rls")
    if context is not None and connection.dialect.name == "postgresql":
        connection.execute(_CONTEXT_SQL, context)


def _set_context(session: Session, company_id: str, bypass: bool = False) -> None:
    context = {"cid": company_id, "flag": "on" if bypass else "off"}
    info = getattr(session, "info", None)
    if isinstance(info, dict):
        info["avenqo_rls"] = context
        if session.in_transaction():
            session.execute(_CONTEXT_SQL, context)
        elif hasattr(session, "connection"):
            session.connection()
        return
    session.execute(_CONTEXT_SQL, context)


# Tables that must have PostgreSQL FORCE RLS + tenant policy.
# 0049/0054 cover workspace + voice provisioning. 0056 covers CRM/commerce/
# datasets/audit. 0057 covers invoices, AI conversations and voice calls.
# 0060 expands remaining company_id business tables (reversible; not Production).
TENANT_SCOPED_TABLES = (
    "voice_provisioning_orders",
    "voice_provisioning_claims",
    "voice_telecom_costs",
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
    "billing_invoices",
    "ai_conversations",
    "ai_messages",
    "ai_enterprise_memories",
    "voice_calls",
)

# Additive 0060 set. Users, memberships, auth sessions and global catalogs stay
# unscoped: login and tenant-switch must see rows outside the bound GUC.
RLS_EXPANSION_0060 = (
    "ai_message_sources",
    "ai_support_conversations",
    "ai_support_messages",
    "ai_support_message_sources",
    "ai_tool_execution_records",
    "ai_tool_confirmation_challenges",
    "ai_jobs",
    "tenant_ai_usage",
    "tenant_ai_credit_balances",
    "tenant_ai_credit_reservations",
    "tenant_ai_credit_ledger",
    "tenant_ai_provider_attempts",
    "ai_credit_purchases",
    "billing_accounts",
    "billing_test_documents",
    "enterprise_quotes",
    "enterprise_overrides",
    "voice_phone_numbers",
    "voice_business_configs",
    "voice_tool_actions",
    "voice_caller_credentials",
    "voice_auth_sessions",
    "voice_central_sessions",
    "voice_module_permissions",
    "commerce_oauth_states",
    "normalized_commerce_records",
    "commerce_raw_snapshots",
    "commerce_webhook_receipts",
    "crm_leads",
    "crm_opportunities",
    "crm_activities",
    "crm_contacts",
    "crm_addresses",
    "crm_services",
    "crm_custom_field_definitions",
    "crm_employees",
    "crm_pipelines",
    "crm_communications",
    "crm_reminders",
    "crm_automations",
    "crm_calendar_connections",
    "crm_activity_log",
    "user_source_selections",
    "retail_active_sources",
    "retail_source_states",
    "dataset_profiles",
    "dataset_relationships",
    "data_quality_reports",
    "connector_dataset_evaluations",
    "model_registries",
    "predictions",
    "training_jobs",
    "accounting_transactions",
    "accounting_invoices",
    "company_modules",
    "company_onboarding",
    "company_locale_profiles",
)

TENANT_SCOPED_TABLES = TENANT_SCOPED_TABLES + RLS_EXPANSION_0060


DATASET_CHILD_TABLES = (
    "dataset_profiles",
    "dataset_versions",
    "data_quality_reports",
    "mappings",
)

# Hardened policy: strictly enforces tenant isolation with NO app.bypass_rls backdoor.
_POLICY_SQL = """
CREATE POLICY {table}_tenant_isolation ON {table}
USING (company_id = avenqo_tenant_id())
WITH CHECK (company_id = avenqo_tenant_id())
"""

# Child dataset tables without direct company_id: scoped via datasets relation.
_DATASET_CHILD_POLICY_SQL = """
CREATE POLICY {table}_tenant_isolation ON {table}
USING (dataset_id IN (SELECT id FROM datasets WHERE company_id = avenqo_tenant_id()))
WITH CHECK (dataset_id IN (SELECT id FROM datasets WHERE company_id = avenqo_tenant_id()))
"""

_COMMERCE_RESOLVER_SQL = """
CREATE OR REPLACE FUNCTION public.resolve_commerce_connection_tenant(
    p_provider text,
    p_identifier text
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
STABLE
SET search_path = public, pg_temp
AS $$
DECLARE
    v_company_id uuid;
BEGIN
    SELECT company_id INTO v_company_id
    FROM commerce_connections
    WHERE provider = p_provider
      AND (
          lower(external_account_id) = lower(p_identifier)
          OR (id::text = p_identifier)
      )
      AND status != 'disconnected'
    LIMIT 1;

    RETURN v_company_id;
END;
$$;
"""


def harden_all_tenant_rls_policies(connection) -> None:
    """Harden RLS on all scoped tables and dataset children, removing bypass_rls door."""
    if connection.dialect.name != "postgresql":
        return

    # 1. Create secure resolver function for inbound commerce webhooks
    connection.execute(text(_COMMERCE_RESOLVER_SQL))
    connection.execute(text("GRANT EXECUTE ON FUNCTION public.resolve_commerce_connection_tenant(text, text) TO PUBLIC"))

    inspector = inspect(connection)

    # 2. Re-create hardened RLS on all direct company_id tables
    for table in TENANT_SCOPED_TABLES:
        if not inspector.has_table(table):
            continue
        columns = {column["name"] for column in inspector.get_columns(table)}
        if "company_id" not in columns:
            continue
        connection.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        connection.execute(text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        # Drop any and all existing policies on this table
        existing_policies = connection.execute(
            text("SELECT policyname FROM pg_policies WHERE schemaname = 'public' AND tablename = :t"),
            {"t": table},
        ).fetchall()
        for p in existing_policies:
            connection.execute(text(f'DROP POLICY IF EXISTS "{p[0]}" ON {table}'))
        connection.execute(text(_POLICY_SQL.format(table=table)))

    # 3. Secure child dataset tables
    for table in DATASET_CHILD_TABLES:
        if not inspector.has_table(table):
            continue
        columns = {column["name"] for column in inspector.get_columns(table)}
        if "dataset_id" not in columns:
            continue
        connection.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        connection.execute(text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        existing_policies = connection.execute(
            text("SELECT policyname FROM pg_policies WHERE schemaname = 'public' AND tablename = :t"),
            {"t": table},
        ).fetchall()
        for p in existing_policies:
            connection.execute(text(f'DROP POLICY IF EXISTS "{p[0]}" ON {table}'))
        connection.execute(text(_DATASET_CHILD_POLICY_SQL.format(table=table)))


def revert_harden_all_tenant_rls_policies(connection) -> None:
    """Reversible rollback for migration downgrades."""
    if connection.dialect.name != "postgresql":
        return

    # Drop child policies
    for table in DATASET_CHILD_TABLES:
        connection.execute(text(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}"))
        connection.execute(text(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY"))
        connection.execute(text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))

    connection.execute(text("DROP FUNCTION IF EXISTS public.resolve_commerce_connection_tenant(text, text)"))


def apply_force_rls_policies(connection, tables: tuple[str, ...]) -> None:
    """ENABLE + FORCE RLS with default-deny tenant policy. PostgreSQL only."""

    if connection.dialect.name != "postgresql":
        return
    inspector = inspect(connection)
    for table in tables:
        if not inspector.has_table(table):
            continue
        columns = {column["name"] for column in inspector.get_columns(table)}
        if "company_id" not in columns:
            continue
        connection.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        connection.execute(text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        connection.execute(text(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}"))
        connection.execute(text(_POLICY_SQL.format(table=table)))


def revoke_force_rls_policies(connection, tables: tuple[str, ...]) -> None:
    """Reversible companion: drop 0060 policies without touching earlier revisions."""

    if connection.dialect.name != "postgresql":
        return
    inspector = inspect(connection)
    for table in reversed(tables):
        if not inspector.has_table(table):
            continue
        connection.execute(text(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}"))
        connection.execute(text(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY"))
        connection.execute(text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))
