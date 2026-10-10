"""Add Enterprise quote delivery queue and landing-lead columns."""

from alembic import op
import sqlalchemy as sa

revision = "0051_enterprise_quote_deliveries"
down_revision = "0050_mfa_recovery_and_lockout"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    return column in {item["name"] for item in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("enterprise_quotes"):
        additions = {
            "source": sa.Column("source", sa.String(length=32), nullable=False, server_default="dashboard"),
            "company_name": sa.Column("company_name", sa.String(length=255), nullable=True),
            "need": sa.Column("need", sa.String(length=255), nullable=True),
            "notification_status": sa.Column(
                "notification_status", sa.String(length=32), nullable=False, server_default="pending"
            ),
            "acknowledgment_status": sa.Column(
                "acknowledgment_status", sa.String(length=32), nullable=False, server_default="pending"
            ),
            "idempotency_key": sa.Column("idempotency_key", sa.String(length=64), nullable=True),
            "submitted_at": sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        }
        for name, column in additions.items():
            if not _has_column("enterprise_quotes", name):
                op.add_column("enterprise_quotes", column)
        if inspector.dialect.name != "sqlite":
            op.alter_column("enterprise_quotes", "company_id", existing_type=sa.Uuid(), nullable=True)
            existing = {item["name"] for item in inspector.get_indexes("enterprise_quotes")}
            if "ix_enterprise_quotes_idempotency_key" not in existing:
                op.create_index(
                    "ix_enterprise_quotes_idempotency_key",
                    "enterprise_quotes",
                    ["idempotency_key"],
                    unique=True,
                )

    if not inspector.has_table("enterprise_quote_deliveries"):
        op.create_table(
            "enterprise_quote_deliveries",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("quote_id", sa.Uuid(), nullable=False),
            sa.Column("kind", sa.String(length=32), nullable=False),
            sa.Column("recipient", sa.String(length=255), nullable=False),
            sa.Column("idempotency_key", sa.String(length=128), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_error", sa.String(length=500), nullable=True),
            sa.Column("provider_message_id", sa.String(length=128), nullable=True),
            sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["quote_id"], ["enterprise_quotes.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("idempotency_key", name="uq_enterprise_quote_delivery_idempotency"),
        )
        op.create_index(
            "ix_enterprise_quote_deliveries_quote_id",
            "enterprise_quote_deliveries",
            ["quote_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("enterprise_quote_deliveries"):
        op.drop_table("enterprise_quote_deliveries")
