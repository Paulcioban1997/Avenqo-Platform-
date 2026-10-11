"""Company-scoped linguistic profile for every Avenqo module.

Revision ID: 0052_company_locale_profile
Revises: 0048_billing_test_documents

This revision id is intentionally 0052 (not 0049) so it does not collide with
PR #35's 0049 on other branches. down_revision is origin/main head 0048 only.

DO NOT apply this migration to Production or Sandbox live databases from the
implementing agent. Creating the revision FILE is required; applying it to an
active Railway/live DB is not.
"""

from alembic import op
import sqlalchemy as sa


revision = "0052_company_locale_profile"
down_revision = "0048_billing_test_documents"
branch_labels = None
depends_on = None


def upgrade():
    if sa.inspect(op.get_bind()).has_table("company_locale_profiles"):
        return
    op.create_table(
        "company_locale_profiles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Uuid(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("primary_locale", sa.String(length=16), nullable=False),
        sa.Column("secondary_locales", sa.JSON(), nullable=False),
        sa.Column("voice_by_locale", sa.JSON(), nullable=False),
        sa.Column("fallback_policy", sa.String(length=32), nullable=False, server_default="stay_primary"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("company_id", name="uq_company_locale_profile_company"),
    )


def downgrade():
    if sa.inspect(op.get_bind()).has_table("company_locale_profiles"):
        op.drop_table("company_locale_profiles")
