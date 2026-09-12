"""Add immutable commerce raw snapshots.

Revision ID: 0017_canonical_data_layers
Revises: 0016_connector_ai_evaluations
"""

from alembic import op
import sqlalchemy as sa


revision = "0017_canonical_data_layers"
down_revision = "0016_connector_ai_evaluations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("commerce_raw_snapshots"):
        op.create_table(
            "commerce_raw_snapshots",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("company_id", sa.Uuid(), nullable=False),
            sa.Column("connection_id", sa.Uuid(), nullable=False),
            sa.Column("provider", sa.String(length=64), nullable=False),
            sa.Column("entity_type", sa.String(length=64), nullable=False),
            sa.Column("source_record_id", sa.String(length=255), nullable=False),
            sa.Column("payload_hash", sa.String(length=64), nullable=False),
            sa.Column("raw_payload", sa.JSON(), nullable=False),
            sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("observed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["connection_id"], ["commerce_connections.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "connection_id",
                "entity_type",
                "source_record_id",
                "payload_hash",
                name="uq_commerce_raw_snapshot_payload",
            ),
        )
        op.create_index("ix_commerce_raw_snapshots_company_id", "commerce_raw_snapshots", ["company_id"])
        op.create_index("ix_commerce_raw_snapshots_connection_id", "commerce_raw_snapshots", ["connection_id"])
        op.create_index("ix_commerce_raw_snapshots_entity_type", "commerce_raw_snapshots", ["entity_type"])

    columns = {
        column["name"]
        for column in sa.inspect(bind).get_columns("normalized_commerce_records")
    }
    if "source_snapshot_id" not in columns:
        op.add_column(
            "normalized_commerce_records",
            sa.Column("source_snapshot_id", sa.Uuid(), nullable=True),
        )
        if bind.dialect.name != "sqlite":
            op.create_foreign_key(
                "fk_normalized_commerce_source_snapshot",
                "normalized_commerce_records",
                "commerce_raw_snapshots",
                ["source_snapshot_id"],
                ["id"],
                ondelete="SET NULL",
            )
        op.create_index(
            "ix_normalized_commerce_records_source_snapshot_id",
            "normalized_commerce_records",
            ["source_snapshot_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {
        column["name"]
        for column in inspector.get_columns("normalized_commerce_records")
    }
    if "source_snapshot_id" in columns:
        op.drop_index(
            "ix_normalized_commerce_records_source_snapshot_id",
            table_name="normalized_commerce_records",
        )
        if bind.dialect.name != "sqlite":
            op.drop_constraint(
                "fk_normalized_commerce_source_snapshot",
                "normalized_commerce_records",
                type_="foreignkey",
            )
        op.drop_column("normalized_commerce_records", "source_snapshot_id")
    if inspector.has_table("commerce_raw_snapshots"):
        op.drop_table("commerce_raw_snapshots")