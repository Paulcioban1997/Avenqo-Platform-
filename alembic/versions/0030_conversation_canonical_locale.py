"""Persist canonical locale continuity for AI conversations.

Revision ID: 0030_conversation_canonical_locale
Revises: 0029_ai_usage_attribution_and_pricing_snapshot
"""

from alembic import op
import sqlalchemy as sa


revision = "0030_conversation_canonical_locale"
down_revision = "0029_ai_usage_attribution_and_pricing_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("ai_conversations")}
    if "locale" not in columns:
        with op.batch_alter_table("ai_conversations") as batch_op:
            batch_op.add_column(
                sa.Column("locale", sa.String(length=16), nullable=False, server_default="fr")
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("ai_conversations")}
    if "locale" in columns:
        with op.batch_alter_table("ai_conversations") as batch_op:
            batch_op.drop_column("locale")
