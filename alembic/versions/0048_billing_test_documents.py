"""Tenant-scoped sandbox document archive, separate from production accounting."""
from alembic import op
import sqlalchemy as sa

revision = "0048_billing_test_documents"
down_revision = "0047_credit_pack_catalog"
branch_labels = None
depends_on = None

def upgrade():
    if sa.inspect(op.get_bind()).has_table("billing_test_documents"):
        return
    op.create_table("billing_test_documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("source_invoice_id", sa.String(255), nullable=False),
        sa.Column("source_company_id", sa.String(36), nullable=False),
        sa.Column("number", sa.String(100), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("total", sa.BigInteger(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pdf_sha256", sa.String(64), nullable=False),
        sa.Column("pdf_content", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("company_id", "source_invoice_id", name="uq_test_document_source"),
        sa.CheckConstraint("total >= 0", name="ck_test_document_total_nonnegative"))

def downgrade():
    op.drop_table("billing_test_documents")
