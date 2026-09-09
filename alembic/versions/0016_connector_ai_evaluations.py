"""Add durable connector generation evaluation queue.

Revision ID: 0016_connector_ai_evaluations
Revises: 0015_retail_active_sources
"""

from alembic import op
import sqlalchemy as sa


revision = "0016_connector_ai_evaluations"
down_revision = "0015_retail_active_sources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    training_columns = {column["name"] for column in inspector.get_columns("training_jobs")}
    for name, column in (
        (
            "dataset_generation",
            sa.Column("dataset_generation", sa.Integer(), server_default="1", nullable=False),
        ),
        ("module_code", sa.Column("module_code", sa.String(length=100), nullable=True)),
        ("task_code", sa.Column("task_code", sa.String(length=100), nullable=True)),
        ("source_connection_id", sa.Column("source_connection_id", sa.Uuid(), nullable=True)),
    ):
        if name not in training_columns:
            op.add_column("training_jobs", column)
    if "source_connection_id" not in training_columns and bind.dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_training_jobs_source_connection",
            "training_jobs",
            "commerce_connections",
            ["source_connection_id"],
            ["id"],
            ondelete="SET NULL",
        )
    for name, columns in (
        ("ix_training_jobs_dataset_generation", ["dataset_generation"]),
        ("ix_training_jobs_module_code", ["module_code"]),
        ("ix_training_jobs_task_code", ["task_code"]),
        ("ix_training_jobs_source_connection_id", ["source_connection_id"]),
    ):
        if name not in {index["name"] for index in inspector.get_indexes("training_jobs")}:
            op.create_index(name, "training_jobs", columns, unique=False)
    existing_training_indexes = {
        index["name"] for index in sa.inspect(bind).get_indexes("training_jobs")
    }
    for name, columns, predicate in (
        (
            "uq_training_jobs_active_dataset_task",
            ["company_id", "dataset_id", "module_code", "task_code"],
            "status IN ('PENDING', 'RUNNING')",
        ),
    ):
        if name not in existing_training_indexes:
            op.create_index(
                name,
                "training_jobs",
                columns,
                unique=True,
                postgresql_where=sa.text(predicate),
                sqlite_where=sa.text(predicate),
            )

    if inspector.has_table("connector_dataset_evaluations"):
        return
    evaluation_status = sa.Enum(
        "PENDING",
        "CLAIMED",
        "COMPLETED",
        "FAILED",
        "COALESCED",
        name="dataset_evaluation_status",
    )
    evaluation_status.create(bind, checkfirst=True)
    op.create_table(
        "connector_dataset_evaluations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_generation", sa.Integer(), nullable=False),
        sa.Column("changed_records", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", evaluation_status, nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_token", sa.Uuid(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision", sa.String(length=64), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("drift_metrics", sa.JSON(), nullable=True),
        sa.Column("ai_job_ids", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["connection_id"], ["commerce_connections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "connection_id",
            "dataset_id",
            "dataset_generation",
            name="uq_connector_dataset_evaluation_generation",
        ),
    )
    op.create_index(
        "ix_connector_dataset_evaluations_company_id",
        "connector_dataset_evaluations",
        ["company_id"],
    )
    op.create_index(
        "ix_connector_dataset_evaluations_connection_id",
        "connector_dataset_evaluations",
        ["connection_id"],
    )
    op.create_index(
        "ix_connector_dataset_evaluations_dataset_id",
        "connector_dataset_evaluations",
        ["dataset_id"],
    )
    op.create_index(
        "ix_connector_dataset_evaluations_status",
        "connector_dataset_evaluations",
        ["status"],
    )
    op.create_index(
        "ix_connector_dataset_evaluations_due",
        "connector_dataset_evaluations",
        ["status", "due_at", "lease_expires_at"],
    )


def downgrade() -> None:
    op.drop_table("connector_dataset_evaluations")
    bind = op.get_bind()
    sa.Enum(name="dataset_evaluation_status").drop(bind, checkfirst=True)
    for name in (
        "uq_training_jobs_active_dataset_task",
        "ix_training_jobs_source_connection_id",
        "ix_training_jobs_task_code",
        "ix_training_jobs_module_code",
        "ix_training_jobs_dataset_generation",
    ):
        op.drop_index(name, table_name="training_jobs")
    if bind.dialect.name != "sqlite":
        op.drop_constraint("fk_training_jobs_source_connection", "training_jobs", type_="foreignkey")
    for name in ("source_connection_id", "task_code", "module_code", "dataset_generation"):
        op.drop_column("training_jobs", name)