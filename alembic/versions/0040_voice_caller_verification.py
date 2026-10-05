"""Add server-side voice caller classification and OTP challenge state."""

from alembic import op
import sqlalchemy as sa

revision = "0040_voice_caller_verification"
down_revision = "0039_voice_phone_numbers"
branch_labels = None
depends_on = None


_COLUMNS = (
    sa.Column("caller_type", sa.String(16), nullable=False, server_default="UNKNOWN"),
    sa.Column("authenticated_user_id", sa.Uuid(), sa.ForeignKey("users.id", name="fk_voice_call_authenticated_user", ondelete="SET NULL"), nullable=True),
    sa.Column("verified_client_id", sa.Uuid(), sa.ForeignKey("crm_clients.id", name="fk_voice_call_verified_client", ondelete="SET NULL"), nullable=True),
    sa.Column("verification_user_id", sa.Uuid(), sa.ForeignKey("users.id", name="fk_voice_call_verification_user", ondelete="SET NULL"), nullable=True),
    sa.Column("verification_client_id", sa.Uuid(), sa.ForeignKey("crm_clients.id", name="fk_voice_call_verification_client", ondelete="SET NULL"), nullable=True),
    sa.Column("verification_code_hash", sa.String(64), nullable=True),
    sa.Column("verification_expires_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("verification_attempts", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("caller_verified_at", sa.DateTime(timezone=True), nullable=True),
)


def upgrade() -> None:
    bind = op.get_bind()
    existing = {column["name"] for column in sa.inspect(bind).get_columns("voice_calls")}
    with op.batch_alter_table("voice_calls") as batch:
        for column in _COLUMNS:
            if column.name not in existing:
                batch.add_column(column)
    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("voice_calls")}
    for name, column in (
        ("ix_voice_calls_caller_type", "caller_type"),
        ("ix_voice_calls_authenticated_user_id", "authenticated_user_id"),
        ("ix_voice_calls_verified_client_id", "verified_client_id"),
    ):
        if name not in indexes:
            op.create_index(name, "voice_calls", [column])


def downgrade() -> None:
    bind = op.get_bind()
    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("voice_calls")}
    for name in (
        "ix_voice_calls_verified_client_id",
        "ix_voice_calls_authenticated_user_id",
        "ix_voice_calls_caller_type",
    ):
        if name in indexes:
            op.drop_index(name, table_name="voice_calls")
    existing = {column["name"] for column in sa.inspect(bind).get_columns("voice_calls")}
    with op.batch_alter_table("voice_calls") as batch:
        for column in reversed(_COLUMNS):
            if column.name in existing:
                batch.drop_column(column.name)