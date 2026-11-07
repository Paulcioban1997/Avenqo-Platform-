"""Persist secure download nonces for distributed, atomic anti-replay protection.

Revision ID: 0074_secure_download_nonces
Revises: 0073_contract_signing_challenges
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0074_secure_download_nonces"
down_revision = "0073_contract_signing_challenges"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("secure_download_nonces"):
        op.create_table(
            "secure_download_nonces",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("nonce", sa.String(64), nullable=False, unique=True),
            sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("doc_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("doc_type", sa.String(32), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=False),
        )
    existing_indexes = {index["name"] for index in sa.inspect(bind).get_indexes("secure_download_nonces")}
    if "ix_secure_download_nonces_nonce" not in existing_indexes:
        op.create_index("ix_secure_download_nonces_nonce", "secure_download_nonces", ["nonce"], unique=True)
    if "ix_secure_download_nonces_company_id" not in existing_indexes:
        op.create_index("ix_secure_download_nonces_company_id", "secure_download_nonces", ["company_id"])
    if "ix_secure_download_nonces_user_id" not in existing_indexes:
        op.create_index("ix_secure_download_nonces_user_id", "secure_download_nonces", ["user_id"])
    if "ix_secure_download_nonces_expires_at" not in existing_indexes:
        op.create_index("ix_secure_download_nonces_expires_at", "secure_download_nonces", ["expires_at"])


def downgrade() -> None:
    op.drop_table("secure_download_nonces")
