"""Store Stripe invoice plan and billing periods.

Revision ID: 0008_billing_invoice_periods
Revises: 0007_tenant_ai_credit_balances
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008_billing_invoice_periods"
down_revision: Union[str, None] = "0007_tenant_ai_credit_balances"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("billing_invoices", sa.Column("plan_code", sa.String(length=64), nullable=True))
    op.add_column("billing_invoices", sa.Column("period_start", sa.DateTime(timezone=True), nullable=True))
    op.add_column("billing_invoices", sa.Column("period_end", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("billing_invoices", "period_end")
    op.drop_column("billing_invoices", "period_start")
    op.drop_column("billing_invoices", "plan_code")