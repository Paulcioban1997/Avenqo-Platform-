"""Add atomic AI credit reservations, ledger, and durable Stripe purchases.

Revision ID: 0012_ai_credit_economics
Revises: 0011_ai_provider_attempt_ledger
"""

from alembic import op
import sqlalchemy as sa


revision = "0012_ai_credit_economics"
down_revision = "0011_ai_provider_attempt_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    balance_columns = {
        column["name"]
        for column in inspector.get_columns("tenant_ai_credit_balances")
    }
    with op.batch_alter_table("tenant_ai_credit_balances") as batch_op:
        if "included_reserved" not in balance_columns:
            batch_op.add_column(
                sa.Column("included_reserved", sa.Integer(), nullable=False, server_default="0")
            )
        if "purchased_reserved" not in balance_columns:
            batch_op.add_column(
                sa.Column("purchased_reserved", sa.Integer(), nullable=False, server_default="0")
            )
    inspector = sa.inspect(bind)
    balance_checks = {
        constraint["name"]
        for constraint in inspector.get_check_constraints("tenant_ai_credit_balances")
    }
    with op.batch_alter_table("tenant_ai_credit_balances") as batch_op:
        if "ck_ai_credit_included_reserved_nonnegative" not in balance_checks:
            batch_op.create_check_constraint(
                "ck_ai_credit_included_reserved_nonnegative",
                "included_reserved >= 0",
            )
        if "ck_ai_credit_purchased_reserved_nonnegative" not in balance_checks:
            batch_op.create_check_constraint(
                "ck_ai_credit_purchased_reserved_nonnegative",
                "purchased_reserved >= 0",
            )
        if "ck_ai_credit_purchased_reserved_available" not in balance_checks:
            batch_op.create_check_constraint(
                "ck_ai_credit_purchased_reserved_available",
                "purchased_reserved <= purchased_balance",
            )

    if "ai_credit_purchases" not in tables:
        op.create_table(
            "ai_credit_purchases",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("company_id", sa.UUID(), nullable=False),
            sa.Column("stripe_checkout_session_id", sa.String(length=255), nullable=True),
            sa.Column("stripe_payment_intent_id", sa.String(length=255), nullable=True),
            sa.Column("stripe_customer_id", sa.String(length=255), nullable=False),
            sa.Column("pack_code", sa.String(length=64), nullable=False),
            sa.Column("plan_code", sa.String(length=64), nullable=False),
            sa.Column("credits_granted", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("credits_remaining", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("credits_reserved", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("price_usd_cents", sa.Integer(), nullable=False),
            sa.Column("amount_paid", sa.BigInteger(), nullable=True),
            sa.Column("currency", sa.String(length=8), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="creating"),
            sa.Column("refunded_amount", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("credits_reversed", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("refund_shortfall_credits", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("review_required", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.CheckConstraint("credits_granted >= 0", name="ck_ai_credit_purchase_granted_nonnegative"),
            sa.CheckConstraint("credits_remaining >= 0", name="ck_ai_credit_purchase_remaining_nonnegative"),
            sa.CheckConstraint("credits_reserved >= 0", name="ck_ai_credit_purchase_reserved_nonnegative"),
            sa.CheckConstraint("credits_reserved <= credits_remaining", name="ck_ai_credit_purchase_reserved_available"),
            sa.CheckConstraint("price_usd_cents >= 0", name="ck_ai_credit_purchase_price_nonnegative"),
            sa.CheckConstraint("refunded_amount >= 0", name="ck_ai_credit_purchase_refund_nonnegative"),
            sa.CheckConstraint("credits_reversed >= 0", name="ck_ai_credit_purchase_reversed_nonnegative"),
            sa.CheckConstraint("refund_shortfall_credits >= 0", name="ck_ai_credit_purchase_shortfall_nonnegative"),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            op.f("ix_ai_credit_purchases_company_id"),
            "ai_credit_purchases",
            ["company_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_ai_credit_purchases_stripe_checkout_session_id"),
            "ai_credit_purchases",
            ["stripe_checkout_session_id"],
            unique=True,
        )
        op.create_index(
            op.f("ix_ai_credit_purchases_stripe_payment_intent_id"),
            "ai_credit_purchases",
            ["stripe_payment_intent_id"],
            unique=True,
        )
        op.create_index(
            op.f("ix_ai_credit_purchases_stripe_customer_id"),
            "ai_credit_purchases",
            ["stripe_customer_id"],
            unique=False,
        )

    if "tenant_ai_credit_reservations" not in tables:
        op.create_table(
            "tenant_ai_credit_reservations",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("company_id", sa.UUID(), nullable=False),
            sa.Column("avenqo_request_id", sa.String(length=100), nullable=False),
            sa.Column("billing_period", sa.String(length=7), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="reserved"),
            sa.Column("estimated_credits", sa.Integer(), nullable=False),
            sa.Column("reserved_included", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("reserved_purchased", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("actual_credits", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("settled_included", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("settled_purchased", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("unfunded_credits", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("purchase_allocations", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint("estimated_credits > 0", name="ck_ai_credit_reservation_estimate_positive"),
            sa.CheckConstraint("reserved_included >= 0", name="ck_ai_credit_reservation_included_nonnegative"),
            sa.CheckConstraint("reserved_purchased >= 0", name="ck_ai_credit_reservation_purchased_nonnegative"),
            sa.CheckConstraint("actual_credits >= 0", name="ck_ai_credit_reservation_actual_nonnegative"),
            sa.CheckConstraint("settled_included >= 0", name="ck_ai_credit_reservation_settled_included_nonnegative"),
            sa.CheckConstraint("settled_purchased >= 0", name="ck_ai_credit_reservation_settled_purchased_nonnegative"),
            sa.CheckConstraint("unfunded_credits >= 0", name="ck_ai_credit_reservation_unfunded_nonnegative"),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "company_id",
                "avenqo_request_id",
                name="uq_ai_credit_reservation_company_request",
            ),
        )
        op.create_index(
            op.f("ix_tenant_ai_credit_reservations_company_id"),
            "tenant_ai_credit_reservations",
            ["company_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_tenant_ai_credit_reservations_avenqo_request_id"),
            "tenant_ai_credit_reservations",
            ["avenqo_request_id"],
            unique=False,
        )

    if "tenant_ai_credit_ledger" not in tables:
        op.create_table(
            "tenant_ai_credit_ledger",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("company_id", sa.UUID(), nullable=False),
            sa.Column("idempotency_key", sa.String(length=255), nullable=False),
            sa.Column("transaction_type", sa.String(length=50), nullable=False),
            sa.Column("reference_id", sa.String(length=255), nullable=True),
            sa.Column("billing_period", sa.String(length=7), nullable=False),
            sa.Column("included_delta", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("purchased_delta", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("included_reserved_delta", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("purchased_reserved_delta", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("monthly_used_after", sa.Integer(), nullable=False),
            sa.Column("purchased_balance_after", sa.Integer(), nullable=False),
            sa.Column("included_reserved_after", sa.Integer(), nullable=False),
            sa.Column("purchased_reserved_after", sa.Integer(), nullable=False),
            sa.Column("details", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("idempotency_key", name="uq_ai_credit_ledger_idempotency_key"),
        )
        op.create_index(
            op.f("ix_tenant_ai_credit_ledger_company_id"),
            "tenant_ai_credit_ledger",
            ["company_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_tenant_ai_credit_ledger_transaction_type"),
            "tenant_ai_credit_ledger",
            ["transaction_type"],
            unique=False,
        )
        op.create_index(
            op.f("ix_tenant_ai_credit_ledger_reference_id"),
            "tenant_ai_credit_ledger",
            ["reference_id"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "tenant_ai_credit_ledger" in tables:
        op.drop_table("tenant_ai_credit_ledger")
    if "tenant_ai_credit_reservations" in tables:
        op.drop_table("tenant_ai_credit_reservations")
    if "ai_credit_purchases" in tables:
        op.drop_table("ai_credit_purchases")

    balance_columns = {
        column["name"]
        for column in inspector.get_columns("tenant_ai_credit_balances")
    }
    balance_checks = {
        constraint["name"]
        for constraint in inspector.get_check_constraints("tenant_ai_credit_balances")
    }
    with op.batch_alter_table("tenant_ai_credit_balances") as batch_op:
        for constraint_name in (
            "ck_ai_credit_purchased_reserved_available",
            "ck_ai_credit_purchased_reserved_nonnegative",
            "ck_ai_credit_included_reserved_nonnegative",
        ):
            if constraint_name in balance_checks:
                batch_op.drop_constraint(constraint_name, type_="check")
        if "purchased_reserved" in balance_columns:
            batch_op.drop_column("purchased_reserved")
        if "included_reserved" in balance_columns:
            batch_op.drop_column("included_reserved")
