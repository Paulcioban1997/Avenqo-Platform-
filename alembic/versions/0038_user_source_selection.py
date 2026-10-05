"""Persist authenticated user's data context separately from activation."""

from alembic import op
import sqlalchemy as sa

revision = "0038_user_source_selection"
down_revision = "0037_tenant_business_hours"
branch_labels = None
depends_on = None


def upgrade():
    if "user_source_selections" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table("user_source_selections",
            sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("source_type", sa.String(20), nullable=False),
            sa.Column("dataset_id", sa.Uuid(), nullable=True),
            sa.Column("connection_id", sa.Uuid(), nullable=True))


def downgrade():
    op.drop_table("user_source_selections")