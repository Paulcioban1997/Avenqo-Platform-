"""Add employee_leaves and employee_performance_reviews tables for HR module.

Revision ID: 0087_hr_module_tables
Revises: 0086_voice_ai_coach_config
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0087_hr_module_tables"
down_revision = "0086_voice_ai_coach_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "employee_leaves" not in tables:
        op.create_table(
            "employee_leaves",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("leave_type", sa.String(32), nullable=False, server_default="vacation"),
            sa.Column("start_date", sa.DateTime(timezone=True), nullable=False),
            sa.Column("end_date", sa.DateTime(timezone=True), nullable=False),
            sa.Column("days_count", sa.Float(), nullable=False, server_default="1.0"),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
            sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    if "employee_performance_reviews" not in tables:
        op.create_table(
            "employee_performance_reviews",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("reviewer_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("review_period", sa.String(64), nullable=False, server_default="2026"),
            sa.Column("rating", sa.Float(), nullable=False, server_default="4.5"),
            sa.Column("strengths", sa.Text(), nullable=True),
            sa.Column("growth_areas", sa.Text(), nullable=True),
            sa.Column("goals", sa.Text(), nullable=True),
            sa.Column("ai_coach_notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "employee_performance_reviews" in tables:
        op.drop_table("employee_performance_reviews")
    if "employee_leaves" in tables:
        op.drop_table("employee_leaves")
