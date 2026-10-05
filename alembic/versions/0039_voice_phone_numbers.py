"""Persist provider-neutral, tenant-assigned voice numbers."""

from alembic import op
import sqlalchemy as sa

revision = "0039_voice_phone_numbers"
down_revision = "0038_user_source_selection"
branch_labels = None
depends_on = None


def upgrade():
    if "voice_phone_numbers" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            "voice_phone_numbers",
            sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
            sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
            sa.Column("config_id", sa.Uuid(), sa.ForeignKey("voice_business_configs.id", ondelete="SET NULL"), nullable=True),
            sa.Column("phone_number", sa.String(32), nullable=False),
            sa.Column("country_code", sa.String(2), nullable=False),
            sa.Column("region", sa.String(120), nullable=True),
            sa.Column("locality", sa.String(120), nullable=True),
            sa.Column("provider", sa.String(32), nullable=False, server_default="telnyx"),
            sa.Column("provider_number_id", sa.String(255), nullable=True),
            sa.Column("number_type", sa.String(32), nullable=False),
            sa.Column("capabilities", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("regulatory_status", sa.String(48), nullable=False, server_default="unknown"),
            sa.Column("regulatory_requirements", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("status", sa.String(32), nullable=False, server_default="active"),
            sa.Column("monthly_cost", sa.Numeric(12, 4), nullable=True),
            sa.Column("monthly_cost_currency", sa.String(3), nullable=True),
            sa.Column("purchased_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("phone_number", name="uq_voice_phone_number_e164"),
            sa.UniqueConstraint("provider_number_id", name="uq_voice_provider_number_id"),
        )
    indexes = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes("voice_phone_numbers")}
    for name, column in (
        ("ix_voice_phone_numbers_company_id", "company_id"),
        ("ix_voice_phone_numbers_config_id", "config_id"),
        ("ix_voice_phone_numbers_country_code", "country_code"),
        ("ix_voice_phone_numbers_status", "status"),
    ):
        if name not in indexes:
            op.create_index(name, "voice_phone_numbers", [column])


def downgrade():
    if "voice_phone_numbers" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("voice_phone_numbers")