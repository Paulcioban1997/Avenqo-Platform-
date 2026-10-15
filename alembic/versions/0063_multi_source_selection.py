"""Add selected_source_ids JSON column for multi-source workspace selection.

Revision ID: 0063_multi_source_selection
Revises: 0061b_harden_tenant_rls_no_bypass
"""

from alembic import op
import sqlalchemy as sa

revision = "0063_multi_source_selection"
down_revision = "0061b_harden_tenant_rls_no_bypass"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "retail_active_sources" in tables:
        columns = {c["name"] for c in inspector.get_columns("retail_active_sources")}
        if "selected_source_ids" not in columns:
            op.add_column(
                "retail_active_sources",
                sa.Column("selected_source_ids", sa.JSON(), nullable=False, server_default="[]"),
            )

    if "user_source_selections" in tables:
        columns = {c["name"] for c in inspector.get_columns("user_source_selections")}
        if "selected_source_ids" not in columns:
            op.add_column(
                "user_source_selections",
                sa.Column("selected_source_ids", sa.JSON(), nullable=False, server_default="[]"),
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "retail_active_sources" in tables:
        columns = {c["name"] for c in inspector.get_columns("retail_active_sources")}
        if "selected_source_ids" in columns:
            op.drop_column("retail_active_sources", "selected_source_ids")

    if "user_source_selections" in tables:
        columns = {c["name"] for c in inspector.get_columns("user_source_selections")}
        if "selected_source_ids" in columns:
            op.drop_column("user_source_selections", "selected_source_ids")
