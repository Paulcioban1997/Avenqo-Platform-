"""Persist per-turn Voice language detection and conversation continuity.

Revision ID: 0035_voice_language_continuity
Revises: 0034_voice_audio_frame_sequence
"""

from alembic import op
import sqlalchemy as sa

revision = "0035_voice_language_continuity"
down_revision = "0034_voice_audio_frame_sequence"
branch_labels = None
depends_on = None


_COLUMNS = (
    sa.Column("detected_language", sa.String(length=16), nullable=True),
    sa.Column("detected_locale", sa.String(length=16), nullable=True),
    sa.Column("language_confidence", sa.Float(), nullable=True),
    sa.Column("previous_locale", sa.String(length=16), nullable=True),
)


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("voice_central_sessions")}
    with op.batch_alter_table("voice_central_sessions") as batch_op:
        for column in _COLUMNS:
            if column.name not in columns:
                batch_op.add_column(column)


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("voice_central_sessions")}
    with op.batch_alter_table("voice_central_sessions") as batch_op:
        for column in reversed(_COLUMNS):
            if column.name in columns:
                batch_op.drop_column(column.name)
