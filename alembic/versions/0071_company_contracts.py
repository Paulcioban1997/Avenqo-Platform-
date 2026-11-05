"""Add company_contracts table for legal and SaaS commercial agreements tracking.

Revision ID: 0071_company_contracts
Revises: 0070_employee_invitations_numeric_codes
Create Date: 2026-11-04 14:35:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0071_company_contracts"
down_revision = "0070_employee_invitations_numeric_codes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_contracts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contract_type", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING_SIGNATURE"),
        sa.Column("version", sa.String(32), nullable=False, server_default="2026-V1"),
        sa.Column("language", sa.String(10), nullable=False, server_default="fr"),
        sa.Column("signature_mode", sa.String(32), nullable=True),
        sa.Column("signatory_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("signatory_name", sa.String(255), nullable=True),
        sa.Column("signatory_email", sa.String(255), nullable=True),
        sa.Column("signatory_title", sa.String(255), nullable=True),
        sa.Column("signatory_authority_declared", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sha256_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("content_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("storage_path", sa.String(512), nullable=True),
        sa.Column("audit_receipt_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.UniqueConstraint("company_id", "contract_type", "version", name="uq_company_contracts_type_version"),
    )
    op.create_index("ix_company_contracts_company_id", "company_contracts", ["company_id"])
    op.create_index("ix_company_contracts_contract_type", "company_contracts", ["contract_type"])
    op.create_index("ix_company_contracts_status", "company_contracts", ["status"])


def downgrade() -> None:
    op.drop_index("ix_company_contracts_status", table_name="company_contracts")
    op.drop_index("ix_company_contracts_contract_type", table_name="company_contracts")
    op.drop_index("ix_company_contracts_company_id", table_name="company_contracts")
    op.drop_table("company_contracts")

