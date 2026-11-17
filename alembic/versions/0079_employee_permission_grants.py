"""Store the exact permissions granted to an employee.

Revision ID: 0079_employee_permission_grants
Revises: 0078_sandbox_mailbox

Null means the account keeps the permissions of its role. A stored list
is the only access that account receives. Additive on SQLite and PostgreSQL.
"""

from alembic import op
import sqlalchemy as sa

revision = "0079_employee_permission_grants"
down_revision = "0078_sandbox_mailbox"
branch_labels = None
depends_on = None


def _add(table: str) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(table):
        return
    names = {column["name"] for column in inspector.get_columns(table)}
    if "permission_grants" in names:
        return
    op.add_column(table, sa.Column("permission_grants", sa.Text(), nullable=True))


def upgrade() -> None:
    _add("users")
    _add("employee_invitations")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table in ("users", "employee_invitations"):
        if not inspector.has_table(table):
            continue
        names = {column["name"] for column in inspector.get_columns(table)}
        if "permission_grants" in names:
            op.drop_column(table, "permission_grants")
