"""tenant AI credit balances

Revision ID: 0007_tenant_ai_credit_balances
Revises: 0006_dataset_relationships
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007_tenant_ai_credit_balances"
down_revision: Union[str, None] = "0006_dataset_relationships"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenant_ai_credit_balances",
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("monthly_period", sa.String(length=7), nullable=False),
        sa.Column("monthly_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("purchased_balance", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("monthly_used >= 0", name="ck_ai_credit_monthly_used_nonnegative"),
        sa.CheckConstraint("purchased_balance >= 0", name="ck_ai_credit_purchased_nonnegative"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("company_id"),
    )


def downgrade() -> None:
    op.drop_table("tenant_ai_credit_balances")