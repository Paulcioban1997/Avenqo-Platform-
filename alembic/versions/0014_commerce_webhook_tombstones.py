"""Persist deleted commerce resource identifiers.

Revision ID: 0014_commerce_webhook_tombstones
Revises: 0013_commerce_connectors
"""

from alembic import op
import sqlalchemy as sa


revision = "0014_commerce_webhook_tombstones"
down_revision = "0013_commerce_connectors"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "commerce_webhook_receipts" not in tables:
        return
    columns = {
        column["name"]
        for column in inspector.get_columns("commerce_webhook_receipts")
    }
    if "source_record_id" not in columns:
        op.add_column(
            "commerce_webhook_receipts",
            sa.Column("source_record_id", sa.String(length=255), nullable=True),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "commerce_webhook_receipts" not in tables:
        return
    columns = {
        column["name"]
        for column in inspector.get_columns("commerce_webhook_receipts")
    }
    if "source_record_id" in columns:
        op.drop_column("commerce_webhook_receipts", "source_record_id")