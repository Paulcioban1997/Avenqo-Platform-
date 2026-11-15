"""Store each employee's demo Trading watchlist inside their company.

Revision ID: 0082_trading_watch_items
Revises: 0081_email_correction_release

Symbols only. No market prices are persisted. Additive on SQLite and PostgreSQL.
"""

from alembic import op
import sqlalchemy as sa

revision = "0082_trading_watch_items"
down_revision = "0081_email_correction_release"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("trading_watch_items"):
        return
    op.create_table(
        "trading_watch_items",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "user_id", "symbol", name="uq_trading_watch_company_user_symbol"),
    )
    op.create_index("ix_trading_watch_items_company_id", "trading_watch_items", ["company_id"])
    op.create_index("ix_trading_watch_items_user_id", "trading_watch_items", ["user_id"])
    if bind.dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE trading_watch_items ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE trading_watch_items FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY trading_watch_items_tenant_isolation
        ON trading_watch_items
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
    if not inspector.has_table("trading_watch_items"):
        return
    if bind.dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS trading_watch_items_tenant_isolation ON trading_watch_items")
    op.drop_table("trading_watch_items")
