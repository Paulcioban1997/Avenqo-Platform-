"""Add evidence-based cardinality classification to dataset relationships.

Revision ID: 0010_dataset_relationship_cardinality
Revises: 0009_billing_invoice_fiscal_fields
"""

from alembic import op
import sqlalchemy as sa

revision = "0010_dataset_relationship_cardinality"
down_revision = "0009_billing_invoice_fiscal_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("dataset_relationships")}
    if "cardinality" in columns:
        return
    op.add_column(
        "dataset_relationships",
        sa.Column("cardinality", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("dataset_relationships")}
    if "cardinality" in columns:
        op.drop_column("dataset_relationships", "cardinality")
