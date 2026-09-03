"""Store authoritative Stripe invoice fiscal details.

Revision ID: 0009_billing_invoice_fiscal_fields
Revises: 0008_billing_invoice_periods
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0009_billing_invoice_fiscal_fields"
down_revision: Union[str, None] = "0008_billing_invoice_periods"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("billing_invoices", sa.Column("stripe_subscription_id", sa.String(length=255), nullable=True))
    op.add_column("billing_invoices", sa.Column("stripe_customer_id", sa.String(length=255), nullable=True))
    op.add_column("billing_invoices", sa.Column("subtotal", sa.BigInteger(), server_default="0", nullable=False))
    op.add_column("billing_invoices", sa.Column("discount_total", sa.BigInteger(), server_default="0", nullable=False))
    op.add_column("billing_invoices", sa.Column("tax_total", sa.BigInteger(), server_default="0", nullable=False))
    op.add_column("billing_invoices", sa.Column("total", sa.BigInteger(), server_default="0", nullable=False))
    op.add_column("billing_invoices", sa.Column("line_items", sa.JSON(), server_default="[]", nullable=False))
    op.add_column("billing_invoices", sa.Column("billing_details", sa.JSON(), server_default="{}", nullable=False))
    op.add_column("billing_invoices", sa.Column("tax_identifiers", sa.JSON(), server_default="[]", nullable=False))
    op.add_column("billing_invoices", sa.Column("customer_email", sa.String(length=255), nullable=True))
    op.add_column("billing_invoices", sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("billing_invoices", sa.Column("due_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("billing_invoices", sa.Column("email_sent_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_billing_invoices_stripe_subscription_id", "billing_invoices", ["stripe_subscription_id"])
    op.create_index("ix_billing_invoices_stripe_customer_id", "billing_invoices", ["stripe_customer_id"])


def downgrade() -> None:
    op.drop_index("ix_billing_invoices_stripe_customer_id", table_name="billing_invoices")
    op.drop_index("ix_billing_invoices_stripe_subscription_id", table_name="billing_invoices")
    for column in (
        "email_sent_at",
        "due_at",
        "paid_at",
        "customer_email",
        "tax_identifiers",
        "billing_details",
        "line_items",
        "total",
        "tax_total",
        "discount_total",
        "subtotal",
        "stripe_customer_id",
        "stripe_subscription_id",
    ):
        op.drop_column("billing_invoices", column)