"""Add tenant-scoped Voice Central sessions without storing raw audio.

Revision ID: 0032_voice_central_sessions
Revises: 0031_ai_tool_confirmation_challenges
"""

from alembic import op
import sqlalchemy as sa

revision = "0032_voice_central_sessions"
down_revision = "0031_ai_tool_confirmation_challenges"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("voice_central_sessions"):
        op.create_table(
            "voice_central_sessions",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("company_id", sa.UUID(), nullable=False),
            sa.Column("user_id", sa.UUID(), nullable=False),
            sa.Column("conversation_id", sa.UUID(), nullable=False),
            sa.Column("request_id", sa.String(length=100), nullable=False),
            sa.Column("locale", sa.String(length=16), nullable=False),
            sa.Column("stt_provider", sa.String(length=64), nullable=True),
            sa.Column("tts_provider", sa.String(length=64), nullable=True),
            sa.Column("realtime_provider", sa.String(length=64), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
            sa.Column("stt_input_seconds", sa.Float(), nullable=False, server_default="0"),
            sa.Column("tts_output_seconds", sa.Float(), nullable=False, server_default="0"),
            sa.Column("interruption_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["conversation_id"], ["ai_conversations.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("company_id", "request_id", name="uq_voice_central_session_request"),
        )
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("voice_central_sessions")}
    for name, column in (("company_id", "company_id"), ("user_id", "user_id"), ("conversation_id", "conversation_id")):
        index_name = f"ix_voice_central_sessions_{name}"
        if index_name not in indexes:
            op.create_index(index_name, "voice_central_sessions", [column], unique=False)
            indexes.add(index_name)


def downgrade() -> None:
    for name in ("conversation_id", "user_id", "company_id"):
        op.drop_index(f"ix_voice_central_sessions_{name}", table_name="voice_central_sessions")
    op.drop_table("voice_central_sessions")
