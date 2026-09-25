"""Persist independently enabled tenant retail data sources."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0021_retail_source_states"
down_revision = "0020_memberships_and_connector_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "retail_source_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_key", sa.String(length=100), nullable=False),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["connection_id"], ["commerce_connections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "source_key", name="uq_retail_source_state_key"),
    )
    op.create_index(
        "ix_retail_source_states_company_id",
        "retail_source_states",
        ["company_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_retail_source_states_company_id", table_name="retail_source_states")
    op.drop_table("retail_source_states")