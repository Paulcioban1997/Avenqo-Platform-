"""Persist tenant-bound signing challenges for atomic, cross-worker consumption.

Revision ID: 0073_contract_signing_challenges
Revises: 0072_enterprise_agreements_and_legal_profiles
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0073_contract_signing_challenges"
down_revision = "0072_enterprise_agreements_and_legal_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("company_contracts", sa.Column("pdf_sha256", sa.String(64), nullable=True))
    op.create_table(
        "contract_signing_challenges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("contract_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("company_contracts.id"), nullable=False),
        sa.Column("contract_version", sa.String(32), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("commercial_hash", sa.String(64), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("salt", sa.String(64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_contract_signing_challenges_company_id", "contract_signing_challenges", ["company_id"])


def downgrade() -> None:
    op.drop_index("ix_contract_signing_challenges_company_id", table_name="contract_signing_challenges")
    op.drop_table("contract_signing_challenges")
    op.drop_column("company_contracts", "pdf_sha256")
