from alembic.config import Config
from alembic.script import ScriptDirectory
from backend.app.services.tenant_rls import (
    TENANT_SCOPED_TABLES,
    DATASET_CHILD_TABLES,
)


def test_0061b_migration_integrity() -> None:
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    assert script.get_heads() == ["0061b_harden_tenant_rls_no_bypass"]
    
    rev = script.get_revision("0061b_harden_tenant_rls_no_bypass")
    assert rev.down_revision == "0061_tenant_hotpath_indexes"
    idx = script.get_revision("0061_tenant_hotpath_indexes")
    assert idx.down_revision == "0060_rls_remaining_tenant_tables"
    r60 = script.get_revision("0060_rls_remaining_tenant_tables")
    assert r60.down_revision == "0059_migrate_role_schema_create"
    
    # Verify module and functions
    assert hasattr(rev.module, "upgrade")
    assert hasattr(rev.module, "downgrade")
    assert "harden_all_tenant_rls_policies" in rev.module.upgrade.__code__.co_names
    assert "revert_harden_all_tenant_rls_policies" in rev.module.downgrade.__code__.co_names
    
    # Verify scoped tables are defined and protected
    assert len(TENANT_SCOPED_TABLES) >= 70
    assert len(DATASET_CHILD_TABLES) == 4
    assert "crm_notes" in TENANT_SCOPED_TABLES
    assert "commerce_connections" in TENANT_SCOPED_TABLES

