"""Persist structured company signup profile fields.

Revision ID: 0004_company_signup_profile
Revises: 0003_company_onboarding
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_company_signup_profile"
down_revision = "0003_company_onboarding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    company_columns = {column["name"] for column in inspector.get_columns("companies")}
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    additions = (
        ("companies", "website", sa.String(length=255), True, None),
        ("companies", "billing_email", sa.String(length=255), False, ""),
        ("companies", "region", sa.String(length=100), False, "North America"),
        ("companies", "company_size", sa.String(length=50), False, "1-10"),
        ("companies", "preferred_language", sa.String(length=10), False, "fr"),
        ("users", "job_title", sa.String(length=120), False, "Owner"),
        ("users", "phone", sa.String(length=32), True, None),
    )
    for table, name, column_type, nullable, default in additions:
        existing = company_columns if table == "companies" else user_columns
        if name not in existing:
            op.add_column(
                table,
                sa.Column(name, column_type, nullable=nullable, server_default=default),
            )


def downgrade() -> None:
    op.drop_column("users", "phone")
    op.drop_column("users", "job_title")
    op.drop_column("companies", "preferred_language")
    op.drop_column("companies", "company_size")
    op.drop_column("companies", "region")
    op.drop_column("companies", "website")
    op.drop_column("companies", "billing_email")
