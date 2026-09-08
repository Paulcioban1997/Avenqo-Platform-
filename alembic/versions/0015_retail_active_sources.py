"""Persist the active Retail data source for each tenant.

Revision ID: 0015_retail_active_sources
Revises: 0014_commerce_webhook_tombstones
"""

from alembic import op
import sqlalchemy as sa


revision = "0015_retail_active_sources"
down_revision = "0014_commerce_webhook_tombstones"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "retail_active_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=True),
        sa.Column("connection_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["connection_id"],
            ["commerce_connections.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", name="uq_retail_active_source_company"),
    )
    op.create_index(
        "ix_retail_active_sources_company_id",
        "retail_active_sources",
        ["company_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_retail_active_sources_company_id",
        table_name="retail_active_sources",
    )
    op.drop_table("retail_active_sources")