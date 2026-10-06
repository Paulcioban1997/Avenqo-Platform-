"""Allow tenant Voice setup before an external conversation provider is configured."""

from alembic import op
import sqlalchemy as sa

revision = "0042_voice_optional_audio"
down_revision = "0041_voice_central_call_conversation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {item["name"]: item for item in sa.inspect(op.get_bind()).get_columns("voice_business_configs")}
    with op.batch_alter_table("voice_business_configs") as batch:
        for name, column_type in (("retell_agent_id", sa.String(128)), ("retell_sip_uri", sa.String(512))):
            if not columns[name]["nullable"]:
                batch.alter_column(name, existing_type=column_type, nullable=True)


def downgrade() -> None:
    missing = op.get_bind().execute(sa.text(
        "SELECT count(*) FROM voice_business_configs WHERE retell_agent_id IS NULL OR retell_sip_uri IS NULL"
    )).scalar()
    if missing:
        raise RuntimeError("Cannot restore mandatory audio fields while unconfigured tenant Voice setups exist")
    with op.batch_alter_table("voice_business_configs") as batch:
        batch.alter_column("retell_agent_id", existing_type=sa.String(128), nullable=False)
        batch.alter_column("retell_sip_uri", existing_type=sa.String(512), nullable=False)