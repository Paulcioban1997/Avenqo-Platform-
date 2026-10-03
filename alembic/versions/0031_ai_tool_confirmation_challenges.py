"""Persist one-use natural-language mutation confirmation challenges.

Revision ID: 0031_ai_tool_confirmation_challenges
Revises: 0030_conversation_canonical_locale
"""

from alembic import op
import sqlalchemy as sa

revision = "0031_ai_tool_confirmation_challenges"
down_revision = "0030_conversation_canonical_locale"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("ai_tool_confirmation_challenges"):
        op.create_table(
            "ai_tool_confirmation_challenges",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("company_id", sa.UUID(), nullable=False),
            sa.Column("user_id", sa.UUID(), nullable=False),
            sa.Column("conversation_id", sa.UUID(), nullable=True),
            sa.Column("request_id", sa.String(length=100), nullable=False),
            sa.Column("agent_id", sa.String(length=100), nullable=False),
            sa.Column("tool_name", sa.String(length=128), nullable=False),
            sa.Column("arguments_hash", sa.String(length=64), nullable=False),
            sa.Column("locale", sa.String(length=16), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "company_id", "user_id", "conversation_id", "tool_name", "arguments_hash", "consumed_at",
                name="uq_ai_confirmation_active_action",
            ),
        )
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("ai_tool_confirmation_challenges")}
    for name, column in (
        ("company_id", "company_id"),
        ("user_id", "user_id"),
        ("conversation_id", "conversation_id"),
        ("expires_at", "expires_at"),
    ):
        index_name = f"ix_ai_confirmation_{name}"
        if index_name not in indexes:
            op.create_index(index_name, "ai_tool_confirmation_challenges", [column], unique=False)
            indexes.add(index_name)


def downgrade() -> None:
    for name in ("expires_at", "conversation_id", "user_id", "company_id"):
        op.drop_index(f"ix_ai_confirmation_{name}", table_name="ai_tool_confirmation_challenges")
    op.drop_table("ai_tool_confirmation_challenges")
