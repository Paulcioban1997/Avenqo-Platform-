"""Add tenant AI credit wallet and ledger.

Revision ID: 0006_ai_credit_wallet
Revises: 0005_company_currency_code
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006_ai_credit_wallet"
down_revision = "0005_company_currency_code"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_credit_balances",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("billing_period", sa.String(length=7), nullable=False),
        sa.Column("monthly_allowance", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("monthly_remaining", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("purchased_remaining", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id"),
    )
    op.create_index("ix_ai_credit_balances_company_id", "ai_credit_balances", ["company_id"])

    op.create_table(
        "ai_credit_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("transaction_type", sa.String(length=40), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("reference_id", sa.String(length=255), nullable=True),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reference_id", name="uq_ai_credit_transactions_reference_id"),
    )
    op.create_index("ix_ai_credit_transactions_company_id", "ai_credit_transactions", ["company_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_credit_transactions_company_id", table_name="ai_credit_transactions")
    op.drop_table("ai_credit_transactions")
    op.drop_index("ix_ai_credit_balances_company_id", table_name="ai_credit_balances")
    op.drop_table("ai_credit_balances")
