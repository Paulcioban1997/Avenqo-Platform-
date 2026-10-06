"""Tenant PIN hashes and temporary per-call authentication sessions."""

from alembic import op
import sqlalchemy as sa

revision = "0043_voice_caller_auth"
down_revision = "0042_voice_optional_audio"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("voice_calls")}
    with op.batch_alter_table("voice_calls") as batch:
        if "locale" not in columns:
            batch.add_column(sa.Column("locale", sa.String(16), nullable=True))
        if "pin_challenge_hash" not in columns:
            batch.add_column(sa.Column("pin_challenge_hash", sa.String(64), nullable=True))
        if "pin_challenge_expires_at" not in columns:
            batch.add_column(sa.Column("pin_challenge_expires_at", sa.DateTime(timezone=True), nullable=True))
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "voice_caller_credentials" not in existing:
        op.create_table("voice_caller_credentials",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
            sa.Column("principal_type", sa.String(16), nullable=False),
            sa.Column("principal_id", sa.Uuid(), nullable=False),
            sa.Column("phone_number", sa.String(40), nullable=False),
            sa.Column("pin_hash", sa.Text(), nullable=False),
            sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("company_id", "principal_type", "principal_id", name="uq_voice_caller_credential"),
            sa.UniqueConstraint("company_id", "phone_number", name="uq_voice_caller_credential_phone"),
        )
        op.create_index("ix_voice_caller_credentials_company_id", "voice_caller_credentials", ["company_id"])
    if "voice_auth_sessions" not in existing:
        op.create_table("voice_auth_sessions",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
            sa.Column("call_id", sa.Uuid(), sa.ForeignKey("voice_calls.id", ondelete="CASCADE"), nullable=False),
            sa.Column("caller_type", sa.String(16), nullable=False),
            sa.Column("principal_id", sa.Uuid(), nullable=False),
            sa.Column("permissions", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("authenticated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("call_id", name="uq_voice_auth_session_call"),
        )
        op.create_index("ix_voice_auth_sessions_company_id", "voice_auth_sessions", ["company_id"])


def downgrade() -> None:
    op.drop_table("voice_auth_sessions")
    op.drop_table("voice_caller_credentials")
    with op.batch_alter_table("voice_calls") as batch:
        batch.drop_column("locale")
        batch.drop_column("pin_challenge_hash")
        batch.drop_column("pin_challenge_expires_at")