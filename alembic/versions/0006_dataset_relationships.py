"""Add tenant-scoped dataset relationship catalog.

Revision ID: 0006_dataset_relationships
Revises: 0005_company_currency_code
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006_dataset_relationships"
down_revision = "0005_company_currency_code"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "dataset_relationships" in inspector.get_table_names():
        return
    op.create_table(
        "dataset_relationships",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("left_dataset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("right_dataset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("left_column", sa.String(length=255), nullable=False),
        sa.Column("right_column", sa.String(length=255), nullable=False),
        sa.Column("canonical_field", sa.String(length=255), nullable=False),
        sa.Column("overlap_ratio", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["left_dataset_id"], ["datasets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["right_dataset_id"], ["datasets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "left_dataset_id", "right_dataset_id", "canonical_field",
            name="uq_dataset_relationship_pair_field",
        ),
    )
    op.create_index("ix_dataset_relationships_company_id", "dataset_relationships", ["company_id"])
    op.create_index("ix_dataset_relationships_left_dataset_id", "dataset_relationships", ["left_dataset_id"])
    op.create_index("ix_dataset_relationships_right_dataset_id", "dataset_relationships", ["right_dataset_id"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "dataset_relationships" in inspector.get_table_names():
        op.drop_table("dataset_relationships")