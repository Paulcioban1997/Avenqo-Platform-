"""Add explicit company memberships without granting additional access."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0019_company_memberships"
down_revision = "0019_enterprise_quotes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("company_memberships"):
        return
    roles = ("OWNER", "ADMIN", "MANAGER", "ANALYST", "USER", "VIEWER")
    role_type = sa.Enum(*roles, name="user_role")
    if bind.dialect.name == "postgresql":
        # The users table already owns this enum; never recreate or drop it.
        role_type = postgresql.ENUM(*roles, name="user_role", create_type=False)
    op.create_table(
        "company_memberships",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", role_type, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "company_id", name="uq_user_company_membership"),
    )
    op.create_index("ix_company_memberships_user_id", "company_memberships", ["user_id"])
    op.create_index("ix_company_memberships_company_id", "company_memberships", ["company_id"])


def downgrade() -> None:
    op.drop_table("company_memberships")
