"""Add tenant commerce connector persistence.

Revision ID: 0013_commerce_connectors
Revises: 0012_ai_credit_economics
"""

from alembic import op
import sqlalchemy as sa


revision = "0013_commerce_connectors"
down_revision = "0012_ai_credit_economics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())

    if "commerce_connections" not in tables:
        op.create_table(
            "commerce_connections",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("company_id", sa.UUID(), nullable=False),
            sa.Column("provider", sa.String(length=64), nullable=False),
            sa.Column("external_account_id", sa.String(length=255), nullable=False),
            sa.Column("display_name", sa.String(length=255), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="CONNECTING"),
            sa.Column("encrypted_credentials", sa.Text(), nullable=True),
            sa.Column("granted_scopes", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("capabilities", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("sync_cursor", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("dataset_ids", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("records_processed", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("current_entity", sa.String(length=64), nullable=True),
            sa.Column("error_category", sa.String(length=64), nullable=True),
            sa.Column("access_token_expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("refresh_token_expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("sync_started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_successful_sync", sa.DateTime(timezone=True), nullable=True),
            sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("provider", "external_account_id", name="uq_commerce_connection_provider_account"),
        )
        op.create_index(op.f("ix_commerce_connections_company_id"), "commerce_connections", ["company_id"])
        op.create_index(op.f("ix_commerce_connections_provider"), "commerce_connections", ["provider"])

    if "commerce_oauth_states" not in tables:
        op.create_table(
            "commerce_oauth_states",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("company_id", sa.UUID(), nullable=False),
            sa.Column("actor_user_id", sa.UUID(), nullable=False),
            sa.Column("provider", sa.String(length=64), nullable=False),
            sa.Column("external_account_id", sa.String(length=255), nullable=False),
            sa.Column("state_hash", sa.String(length=64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_commerce_oauth_states_company_id"), "commerce_oauth_states", ["company_id"])
        op.create_index(op.f("ix_commerce_oauth_states_state_hash"), "commerce_oauth_states", ["state_hash"], unique=True)

    if "normalized_commerce_records" not in tables:
        op.create_table(
            "normalized_commerce_records",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("company_id", sa.UUID(), nullable=False),
            sa.Column("connection_id", sa.UUID(), nullable=False),
            sa.Column("provider", sa.String(length=64), nullable=False),
            sa.Column("entity_type", sa.String(length=64), nullable=False),
            sa.Column("source_record_id", sa.String(length=255), nullable=False),
            sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("normalized_data", sa.JSON(), nullable=False),
            sa.Column("deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["connection_id"], ["commerce_connections.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("connection_id", "entity_type", "source_record_id", name="uq_normalized_commerce_connection_entity_record"),
        )
        op.create_index(op.f("ix_normalized_commerce_records_company_id"), "normalized_commerce_records", ["company_id"])
        op.create_index(op.f("ix_normalized_commerce_records_connection_id"), "normalized_commerce_records", ["connection_id"])
        op.create_index(op.f("ix_normalized_commerce_records_entity_type"), "normalized_commerce_records", ["entity_type"])

    if "commerce_webhook_receipts" not in tables:
        op.create_table(
            "commerce_webhook_receipts",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("company_id", sa.UUID(), nullable=False),
            sa.Column("connection_id", sa.UUID(), nullable=False),
            sa.Column("provider", sa.String(length=64), nullable=False),
            sa.Column("webhook_id", sa.String(length=255), nullable=False),
            sa.Column("topic", sa.String(length=120), nullable=False),
            sa.Column("payload_hash", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="RECEIVED"),
            sa.Column("error_category", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["connection_id"], ["commerce_connections.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("provider", "webhook_id", name="uq_commerce_webhook_provider_delivery"),
        )
        op.create_index(op.f("ix_commerce_webhook_receipts_company_id"), "commerce_webhook_receipts", ["company_id"])
        op.create_index(op.f("ix_commerce_webhook_receipts_connection_id"), "commerce_webhook_receipts", ["connection_id"])


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    for table_name in (
        "commerce_webhook_receipts",
        "normalized_commerce_records",
        "commerce_oauth_states",
        "commerce_connections",
    ):
        if table_name in tables:
            op.drop_table(table_name)