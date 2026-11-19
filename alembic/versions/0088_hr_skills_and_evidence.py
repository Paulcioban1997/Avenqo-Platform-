"""Add employee_skills table and audit columns to employee_performance_reviews.

Revision ID: 0088_hr_skills_and_evidence
Revises: 0087_hr_module_tables
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0088_hr_skills_and_evidence"
down_revision = "0087_hr_module_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "employee_skills" not in tables:
        op.create_table(
            "employee_skills",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "company_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("companies.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column(
                "user_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("category", sa.String(64), nullable=False, server_default="Technique"),
            sa.Column("level", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("status", sa.String(32), nullable=False, server_default="not_assessed"),
            sa.Column("evidence_url_or_note", sa.Text(), nullable=True),
            sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "verified_by_user_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    if "employee_performance_reviews" in tables:
        columns = {col["name"] for col in inspector.get_columns("employee_performance_reviews")}
        if "is_demo" not in columns:
            op.add_column(
                "employee_performance_reviews",
                sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false()),
            )
        if "data_sufficient" not in columns:
            op.add_column(
                "employee_performance_reviews",
                sa.Column("data_sufficient", sa.Boolean(), nullable=False, server_default=sa.true()),
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "employee_performance_reviews" in tables:
        columns = {col["name"] for col in inspector.get_columns("employee_performance_reviews")}
        if "data_sufficient" in columns:
            op.drop_column("employee_performance_reviews", "data_sufficient")
        if "is_demo" in columns:
            op.drop_column("employee_performance_reviews", "is_demo")

    if "employee_skills" in tables:
        op.drop_table("employee_skills")
