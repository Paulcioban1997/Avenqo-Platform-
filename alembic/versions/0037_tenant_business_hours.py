"""Tenant business hours independent of telephony provisioning."""

from alembic import op
import sqlalchemy as sa

revision = "0037_tenant_business_hours"
down_revision = "0036_merge_sandbox_membership_ancestry"
branch_labels = None
depends_on = None


def upgrade():
    if "business_hours" not in {column["name"] for column in sa.inspect(op.get_bind()).get_columns("companies")}:
        op.add_column("companies", sa.Column("business_hours", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))


def downgrade():
    op.drop_column("companies", "business_hours")