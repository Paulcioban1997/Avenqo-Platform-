"""MFA recovery codes and login lockout columns."""

from alembic import op
import sqlalchemy as sa

revision = "0050_mfa_recovery_and_lockout"
down_revision = "0049_workspace_security_and_business_os"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    return column in {item["name"] for item in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("users"):
        return
    if not _has_column("users", "mfa_recovery_hashes"):
        op.add_column("users", sa.Column("mfa_recovery_hashes", sa.Text(), nullable=True))
    if not _has_column("users", "failed_login_count"):
        op.add_column("users", sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0"))
    if not _has_column("users", "locked_until"):
        op.add_column("users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("users"):
        return
    if _has_column("users", "locked_until"):
        op.drop_column("users", "locked_until")
    if _has_column("users", "failed_login_count"):
        op.drop_column("users", "failed_login_count")
    if _has_column("users", "mfa_recovery_hashes"):
        op.drop_column("users", "mfa_recovery_hashes")
