"""Add tenant-scoped CRM custom field definitions."""

from alembic import op
import sqlalchemy as sa

revision = "0025_crm_custom_field_definitions"
down_revision = "0024_crm_client_preferred_language"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crm_custom_field_definitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False, server_default="appointment"),
        sa.Column("field_key", sa.String(length=100), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("field_type", sa.String(length=30), nullable=False, server_default="text"),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("industry_template", sa.String(length=80), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "entity_type", "field_key", name="uq_crm_custom_field_tenant_entity_key"),
    )
    op.create_index("ix_crm_custom_field_definitions_company_id", "crm_custom_field_definitions", ["company_id"])
    op.create_index("ix_crm_custom_field_definitions_is_active", "crm_custom_field_definitions", ["is_active"])


def downgrade() -> None:
    op.drop_index("ix_crm_custom_field_definitions_is_active", table_name="crm_custom_field_definitions")
    op.drop_index("ix_crm_custom_field_definitions_company_id", table_name="crm_custom_field_definitions")
    op.drop_table("crm_custom_field_definitions")