"""Per-company Voice AI module/action permissions.

Revision ID: 0053_voice_module_permissions
Revises: 0048_billing_test_documents

DO NOT APPLY ON LIVE DATABASES. Revision file only — no alembic upgrade on
Production or Sandbox. Independent of PR #35 (0049) and PR #38 (0052).
"""

from alembic import op
import sqlalchemy as sa

revision = "0053_voice_module_permissions"
down_revision = "0048_billing_test_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("voice_module_permissions"):
        return
    op.create_table(
        "voice_module_permissions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Uuid(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("module_code", sa.String(64), nullable=False, index=True),
        sa.Column("action_code", sa.String(64), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "granted_by",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("permission_epoch", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("company_id", "module_code", "action_code", name="uq_voice_module_permission"),
    )


def downgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("voice_module_permissions"):
        op.drop_table("voice_module_permissions")
