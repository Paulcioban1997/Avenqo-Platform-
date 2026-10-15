from backend.app.services.tenant_rls import (
    RLS_EXPANSION_0060,
    TENANT_SCOPED_TABLES,
    apply_force_rls_policies,
    revoke_force_rls_policies,
)


class _SQLiteBind:
    dialect = type("D", (), {"name": "sqlite"})()


class _SQLiteConnection:
    dialect = _SQLiteBind.dialect

    def execute(self, *args, **kwargs):
        raise AssertionError("SQLite must not emit RLS DDL")


def test_0060_helpers_are_sqlite_noops() -> None:
    apply_force_rls_policies(_SQLiteConnection(), RLS_EXPANSION_0060)
    revoke_force_rls_policies(_SQLiteConnection(), RLS_EXPANSION_0060)


def test_0060_tables_are_in_tenant_scoped_inventory() -> None:
    assert "tenant_ai_credit_balances" in RLS_EXPANSION_0060
    assert "voice_central_sessions" in RLS_EXPANSION_0060
    assert "normalized_commerce_records" in RLS_EXPANSION_0060
    assert "users" not in RLS_EXPANSION_0060
    assert "company_memberships" not in RLS_EXPANSION_0060
    assert "auth_sessions" not in RLS_EXPANSION_0060
    for table in RLS_EXPANSION_0060:
        assert table in TENANT_SCOPED_TABLES


def test_0060_is_reversible_alembic_head() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(Config("alembic.ini"))
    heads = script.get_heads()
    assert "0061b_harden_tenant_rls_no_bypass" in heads or "0063_multi_source_selection" in heads
    head = script.get_revision("0061b_harden_tenant_rls_no_bypass")
    assert head.down_revision == "0061_tenant_hotpath_indexes"
    idx = script.get_revision("0061_tenant_hotpath_indexes")
    assert idx.down_revision == "0060_rls_remaining_tenant_tables"
    revision = script.get_revision("0060_rls_remaining_tenant_tables")
    assert revision.down_revision == "0059_migrate_role_schema_create"
    source = revision.module.downgrade.__code__.co_names
    assert "revoke_force_rls_policies" in source
    migrate_role = script.get_revision("0059_migrate_role_schema_create")
    assert migrate_role.down_revision == "0058_sandbox_app_db_roles"
    app_roles = script.get_revision("0058_sandbox_app_db_roles")
    assert app_roles.down_revision == "0057_rls_invoices_ai_voice"
