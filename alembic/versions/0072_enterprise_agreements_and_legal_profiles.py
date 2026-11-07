"""Add company_legal_profiles, company_contracts execution columns, and user platform_role.

Revision ID: 0072_enterprise_agreements_and_legal_profiles
Revises: 0071_company_contracts
Create Date: 2026-11-05 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0072_enterprise_agreements_and_legal_profiles"
down_revision = "0071_company_contracts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    # 1. Table company_legal_profiles
    if not sa.inspect(bind).has_table("company_legal_profiles"):
        op.create_table(
        "company_legal_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("legal_name", sa.String(255), nullable=False),
        sa.Column("trade_name", sa.String(255), nullable=True),
        sa.Column("country", sa.String(100), nullable=False),
        sa.Column("province_state", sa.String(100), nullable=False),
        sa.Column("registration_number", sa.String(100), nullable=True),
        sa.Column("business_number", sa.String(100), nullable=True),
        sa.Column("tax_id_gst", sa.String(100), nullable=True),
        sa.Column("tax_id_qst", sa.String(100), nullable=True),
        sa.Column("tax_id_other", sa.String(100), nullable=True),
        sa.Column("registered_address_street", sa.String(255), nullable=False),
        sa.Column("registered_address_city", sa.String(100), nullable=False),
        sa.Column("registered_address_state_province", sa.String(100), nullable=False),
        sa.Column("registered_address_postal_code", sa.String(32), nullable=False),
        sa.Column("registered_address_country", sa.String(100), nullable=False),
        sa.Column("mailing_address_same", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("mailing_address_street", sa.String(255), nullable=True),
        sa.Column("mailing_address_city", sa.String(100), nullable=True),
        sa.Column("mailing_address_state_province", sa.String(100), nullable=True),
        sa.Column("mailing_address_postal_code", sa.String(32), nullable=True),
        sa.Column("mailing_address_country", sa.String(100), nullable=True),
        sa.Column("website", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(32), nullable=False),
        sa.Column("general_email", sa.String(255), nullable=False),
        sa.Column("billing_email", sa.String(255), nullable=False),
        sa.Column("industry", sa.String(120), nullable=False),
        sa.Column("legal_entity_type", sa.String(100), nullable=False, server_default="Corporation"),
        sa.Column("preferred_language", sa.String(10), nullable=False, server_default="fr"),
        sa.Column("authorized_representative_first_name", sa.String(100), nullable=False),
        sa.Column("authorized_representative_last_name", sa.String(100), nullable=False),
        sa.Column("authorized_representative_email", sa.String(255), nullable=False),
        sa.Column("authorized_representative_title", sa.String(120), nullable=False),
        sa.Column("authorized_representative_capacity", sa.String(100), nullable=False, server_default="Owner"),
        sa.Column("authorized_representative_authority_confirmed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        )
    if "ix_company_legal_profiles_company_id" not in {
        index["name"] for index in sa.inspect(bind).get_indexes("company_legal_profiles")
    }:
        op.create_index("ix_company_legal_profiles_company_id", "company_legal_profiles", ["company_id"])

    # 2. Add columns to company_contracts
    contract_columns = {column["name"] for column in sa.inspect(bind).get_columns("company_contracts")}
    if "execution_state" not in contract_columns:
        op.add_column(
            "company_contracts",
            sa.Column("execution_state", sa.String(32), nullable=False, server_default="PENDING_CUSTOMER"),
        )
    for column in (
        sa.Column("provider_signatory_name", sa.String(255), nullable=True),
        sa.Column("provider_signatory_title", sa.String(255), nullable=True),
        sa.Column("provider_signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_signature_hash", sa.String(64), nullable=True),
        sa.Column("commercial_schedule_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("completion_record_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    ):
        if column.name not in contract_columns:
            op.add_column("company_contracts", column)

    # 3. Add platform_role column to users
    if "platform_role" not in {column["name"] for column in sa.inspect(bind).get_columns("users")}:
        op.add_column("users", sa.Column("platform_role", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "platform_role")
    op.drop_column("company_contracts", "completion_record_json")
    op.drop_column("company_contracts", "commercial_schedule_json")
    op.drop_column("company_contracts", "provider_signature_hash")
    op.drop_column("company_contracts", "provider_signed_at")
    op.drop_column("company_contracts", "provider_signatory_title")
    op.drop_column("company_contracts", "provider_signatory_name")
    op.drop_column("company_contracts", "execution_state")
    op.drop_index("ix_company_legal_profiles_company_id", table_name="company_legal_profiles")
    op.drop_table("company_legal_profiles")
