"""Store Sandbox-only captured mail for the owning company.

Revision ID: 0078_sandbox_mailbox
Revises: 0077_voice_resolver_bypass_rls

Messages never leave the tenant database. PostgreSQL enforces the company
boundary. SQLite tests create the table through the model metadata.
"""

from alembic import op
import sqlalchemy as sa

revision = "0078_sandbox_mailbox"
down_revision = "0077_voice_resolver_bypass_rls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("sandbox_mailbox_messages"):
        return
    op.create_table(
        "sandbox_mailbox_messages",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recipient", sa.String(320), nullable=False),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_sandbox_mailbox_messages_company_id",
        "sandbox_mailbox_messages",
        ["company_id"],
    )
    if bind.dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE sandbox_mailbox_messages ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE sandbox_mailbox_messages FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY sandbox_mailbox_messages_tenant_isolation
        ON sandbox_mailbox_messages
        USING (
          current_setting('app.bypass_rls', true) = 'on'
          OR company_id = avenqo_tenant_id()
        )
        WITH CHECK (
          current_setting('app.bypass_rls', true) = 'on'
          OR company_id = avenqo_tenant_id()
        )
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("sandbox_mailbox_messages"):
        return
    if bind.dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS sandbox_mailbox_messages_tenant_isolation ON sandbox_mailbox_messages")
    op.drop_index("ix_sandbox_mailbox_messages_company_id", table_name="sandbox_mailbox_messages")
    op.drop_table("sandbox_mailbox_messages")
