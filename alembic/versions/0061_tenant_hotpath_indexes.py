"""Additive tenant hot-path indexes for auth, Central AI and CRM.

SQLite-compatible. Does not rewrite rows. Safe to apply on an isolated copy
before any Sandbox GO. Not a Production or live-Sandbox change by itself.
"""

from alembic import op
import sqlalchemy as sa

revision = "0061_tenant_hotpath_indexes"
down_revision = "0060_rls_remaining_tenant_tables"
branch_labels = depends_on = None

INDEXES = (
    ("ix_ai_conversations_company_user", "ai_conversations", ("company_id", "user_id")),
    ("ix_ai_messages_company_conversation", "ai_messages", ("company_id", "conversation_id")),
    ("ix_login_events_company_created", "login_events", ("company_id", "created_at")),
    ("ix_crm_clients_company_email", "crm_clients", ("company_id", "email")),
    ("ix_auth_sessions_user_expires", "auth_sessions", ("user_id", "expires_at")),
)


def _existing_index_names(inspector, table: str) -> set[str]:
    return {item["name"] for item in inspector.get_indexes(table) if item.get("name")}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for name, table, columns in INDEXES:
        if not inspector.has_table(table):
            continue
        if name in _existing_index_names(inspector, table):
            continue
        op.create_index(name, table, list(columns))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for name, table, _columns in INDEXES:
        if not inspector.has_table(table):
            continue
        if name not in _existing_index_names(inspector, table):
            continue
        op.drop_index(name, table_name=table)
