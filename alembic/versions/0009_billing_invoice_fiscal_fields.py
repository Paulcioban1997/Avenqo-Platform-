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
    inspector = sa.inspect(op.get_bind())
    columns = {c["name"] for c in inspector.get_columns("billing_invoices")}
    for name, col in (
        ("stripe_subscription_id", sa.Column("stripe_subscription_id", sa.String(length=255), nullable=True)),
        ("stripe_customer_id", sa.Column("stripe_customer_id", sa.String(length=255), nullable=True)),
        ("subtotal", sa.Column("subtotal", sa.BigInteger(), server_default="0", nullable=False)),
        ("discount_total", sa.Column("discount_total", sa.BigInteger(), server_default="0", nullable=False)),
        ("tax_total", sa.Column("tax_total", sa.BigInteger(), server_default="0", nullable=False)),
        ("total", sa.Column("total", sa.BigInteger(), server_default="0", nullable=False)),
        ("line_items", sa.Column("line_items", sa.JSON(), server_default="[]", nullable=False)),
        ("billing_details", sa.Column("billing_details", sa.JSON(), server_default="{}", nullable=False)),
        ("tax_identifiers", sa.Column("tax_identifiers", sa.JSON(), server_default="[]", nullable=False)),
        ("customer_email", sa.Column("customer_email", sa.String(length=255), nullable=True)),
        ("paid_at", sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True)),
        ("due_at", sa.Column("due_at", sa.DateTime(timezone=True), nullable=True)),
        ("email_sent_at", sa.Column("email_sent_at", sa.DateTime(timezone=True), nullable=True)),
    ):
        if name not in columns:
            op.add_column("billing_invoices", col)
    indexes = {idx["name"] for idx in inspector.get_indexes("billing_invoices")}
    if "ix_billing_invoices_stripe_subscription_id" not in indexes:
        op.create_index("ix_billing_invoices_stripe_subscription_id", "billing_invoices", ["stripe_subscription_id"])
    if "ix_billing_invoices_stripe_customer_id" not in indexes:
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