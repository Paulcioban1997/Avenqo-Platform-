"""Remember which account must release an address before it can be reused.

Revision ID: 0081_email_correction_release
Revises: 0080_employee_email_corrections

The account stays in its company. Only the confirmed inbox can release the
address, and it chooses the replacement. Additive on SQLite and PostgreSQL.
"""

from alembic import op
import sqlalchemy as sa

revision = "0081_email_correction_release"
down_revision = "0080_employee_email_corrections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("employee_email_corrections"):
        return
    names = {column["name"] for column in inspector.get_columns("employee_email_corrections")}
    if "releasing_user_id" in names:
        return
    op.add_column(
        "employee_email_corrections",
        sa.Column("releasing_user_id", sa.Uuid(), nullable=True),
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("employee_email_corrections"):
        return
    names = {column["name"] for column in inspector.get_columns("employee_email_corrections")}
    if "releasing_user_id" in names:
        op.drop_column("employee_email_corrections", "releasing_user_id")
