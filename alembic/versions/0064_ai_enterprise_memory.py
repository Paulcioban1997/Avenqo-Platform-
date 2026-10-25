"""Add ai_enterprise_memories table for persistent enterprise memory.

Revision ID: 0064_ai_enterprise_memory
Revises: 0063_multi_source_selection
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0064_ai_enterprise_memory"
down_revision = "0063_multi_source_selection"
branch_labels = None
depends_on = None


def _is_postgres(bind) -> bool:
    dialect = getattr(bind, "dialect", None)
    return dialect is not None and getattr(dialect, "name", None) == "postgresql"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "ai_enterprise_memories" not in tables:
        op.create_table(
            "ai_enterprise_memories",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("conversation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ai_conversations.id", ondelete="SET NULL"), nullable=True, index=True),
            sa.Column("memory_scope", sa.String(32), nullable=False, server_default="user", index=True),
            sa.Column("memory_type", sa.String(64), nullable=False, server_default="semantic", index=True),
            sa.Column("source_module", sa.String(32), nullable=False, server_default="central", index=True),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("metadata_json", sa.JSON(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true(), index=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

        op.create_index(
            "ix_ai_enterprise_memories_company_active",
            "ai_enterprise_memories",
            ["company_id", "is_active"],
        )

        if _is_postgres(bind):
            op.execute("ALTER TABLE ai_enterprise_memories ENABLE ROW LEVEL SECURITY;")
            op.execute("ALTER TABLE ai_enterprise_memories FORCE ROW LEVEL SECURITY;")
            op.execute(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_policies
                        WHERE tablename = 'ai_enterprise_memories'
                        AND policyname = 'ai_enterprise_memories_tenant_isolation'
                    ) THEN
                        CREATE POLICY ai_enterprise_memories_tenant_isolation
                        ON ai_enterprise_memories
                        USING (company_id::text = current_setting('app.current_company_id', true));
                    END IF;
                END $$;
                """
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "ai_enterprise_memories" in tables:
        if _is_postgres(bind):
            op.execute("DROP POLICY IF EXISTS ai_enterprise_memories_tenant_isolation ON ai_enterprise_memories;")
        op.drop_table("ai_enterprise_memories")
