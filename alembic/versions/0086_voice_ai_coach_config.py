"""Add ai_coach_enabled and ai_coach_config columns to voice_business_configs.

Revision ID: 0086_voice_ai_coach_config
Revises: 0085_reconcile_legacy_demo_stores
"""

from alembic import op
import sqlalchemy as sa

revision = "0086_voice_ai_coach_config"
down_revision = "0085_reconcile_legacy_demo_stores"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"
    inspector = sa.inspect(bind)

    cols = {col["name"] for col in inspector.get_columns("voice_business_configs")}
    with op.batch_alter_table("voice_business_configs") as batch:
        if "ai_coach_enabled" not in cols:
            batch.add_column(
                sa.Column(
                    "ai_coach_enabled",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("true" if is_pg else "1"),
                )
            )
        if "ai_coach_config" not in cols:
            batch.add_column(
                sa.Column(
                    "ai_coach_config",
                    sa.JSON(),
                    nullable=True,
                )
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {col["name"] for col in inspector.get_columns("voice_business_configs")}

    with op.batch_alter_table("voice_business_configs") as batch:
        if "ai_coach_config" in cols:
            batch.drop_column("ai_coach_config")
        if "ai_coach_enabled" in cols:
            batch.drop_column("ai_coach_enabled")
