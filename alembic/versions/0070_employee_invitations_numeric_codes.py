"""Add numeric CSPRNG invitation code columns to employee_invitations.

Revision ID: 0070_employee_invitations_numeric_codes
Revises: 0069_crm_service_approval_columns
"""

from alembic import op
import sqlalchemy as sa

revision = "0070_employee_invitations_numeric_codes"
down_revision = "0069_crm_service_approval_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("employee_invitations"):
        return

    existing_columns = {col["name"] for col in inspector.get_columns("employee_invitations")}
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("employee_invitations")}

    with op.batch_alter_table("employee_invitations") as batch_op:
        if "code_hash" not in existing_columns:
            batch_op.add_column(
                sa.Column("code_hash", sa.String(64), nullable=True)
            )

        if "code_salt" not in existing_columns:
            batch_op.add_column(
                sa.Column("code_salt", sa.String(32), nullable=True)
            )

        if "failed_attempts" not in existing_columns:
            batch_op.add_column(
                sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0")
            )

    # Re-inspect to create index on code_hash if missing
    inspector = sa.inspect(bind)
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("employee_invitations")}
    if "ix_employee_invitations_code_hash" not in existing_indexes:
        op.create_index(
            "ix_employee_invitations_code_hash",
            "employee_invitations",
            ["code_hash"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("employee_invitations"):
        return

    existing_indexes = {idx["name"] for idx in inspector.get_indexes("employee_invitations")}
    if "ix_employee_invitations_code_hash" in existing_indexes:
        op.drop_index("ix_employee_invitations_code_hash", table_name="employee_invitations")

    existing_columns = {col["name"] for col in inspector.get_columns("employee_invitations")}
    with op.batch_alter_table("employee_invitations") as batch_op:
        if "failed_attempts" in existing_columns:
            batch_op.drop_column("failed_attempts")
        if "code_salt" in existing_columns:
            batch_op.drop_column("code_salt")
        if "code_hash" in existing_columns:
            batch_op.drop_column("code_hash")

