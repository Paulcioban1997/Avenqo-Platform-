"""Persist provider connection/order metadata and quoted upfront costs."""

from alembic import op
import sqlalchemy as sa

revision = "0044_voice_number_references"
down_revision = "0043_voice_caller_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("voice_phone_numbers")}
    with op.batch_alter_table("voice_phone_numbers") as batch:
        for name, column_type in (("provider_connection_id", sa.String(255)), ("provider_order_id", sa.String(255)), ("upfront_cost", sa.Numeric(12, 4))):
            if name not in columns:
                batch.add_column(sa.Column(name, column_type, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("voice_phone_numbers") as batch:
        batch.drop_column("provider_connection_id")
        batch.drop_column("provider_order_id")
        batch.drop_column("upfront_cost")