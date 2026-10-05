"""Link verified Voice calls to their tenant Central AI conversation."""

from alembic import op
import sqlalchemy as sa

revision = "0041_voice_central_call_conversation"
down_revision = "0040_voice_caller_verification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("voice_calls")}
    with op.batch_alter_table("voice_calls") as batch:
        if "central_conversation_id" not in columns:
            batch.add_column(sa.Column(
                "central_conversation_id",
                sa.Uuid(),
                sa.ForeignKey("ai_conversations.id", name="fk_voice_call_central_conversation", ondelete="SET NULL"),
                nullable=True,
            ))
        if "source_context" not in columns:
            batch.add_column(sa.Column("source_context", sa.JSON(), nullable=False, server_default="{}"))
    central_columns = {column["name"] for column in sa.inspect(bind).get_columns("voice_central_sessions")}
    if "source_context" not in central_columns:
        with op.batch_alter_table("voice_central_sessions") as batch:
            batch.add_column(sa.Column("source_context", sa.JSON(), nullable=False, server_default="{}"))
    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("voice_calls")}
    if "ix_voice_calls_central_conversation_id" not in indexes:
        op.create_index("ix_voice_calls_central_conversation_id", "voice_calls", ["central_conversation_id"])


def downgrade() -> None:
    bind = op.get_bind()
    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("voice_calls")}
    if "ix_voice_calls_central_conversation_id" in indexes:
        op.drop_index("ix_voice_calls_central_conversation_id", table_name="voice_calls")
    columns = {column["name"] for column in sa.inspect(bind).get_columns("voice_calls")}
    if "central_conversation_id" in columns:
        with op.batch_alter_table("voice_calls") as batch:
            batch.drop_column("central_conversation_id")
    if "source_context" in columns:
        with op.batch_alter_table("voice_calls") as batch:
            batch.drop_column("source_context")
    central_columns = {column["name"] for column in sa.inspect(bind).get_columns("voice_central_sessions")}
    if "source_context" in central_columns:
        with op.batch_alter_table("voice_central_sessions") as batch:
            batch.drop_column("source_context")