"""Unified accounting ledger provenance, proposal governance, and classification rules.

Revision ID: 0089_accounting_unified_ledger_and_proposals
Revises: 0088_hr_skills_and_evidence
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0089_accounting_unified_ledger_and_proposals"
down_revision = "0088_hr_skills_and_evidence"
branch_labels = None
depends_on = None


def _has_index(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    return any(idx.get("name") == index_name for idx in inspector.get_indexes(table_name))


def _has_unique(inspector: sa.Inspector, table_name: str, constraint_name: str) -> bool:
    return any(uq.get("name") == constraint_name for uq in inspector.get_unique_constraints(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    is_sqlite = bind.dialect.name == "sqlite"

    if "accounting_transactions" in tables:
        tx_cols = {col["name"] for col in inspector.get_columns("accounting_transactions")}
        new_tx_cols = [
            ("entry_kind", sa.Column("entry_kind", sa.String(50), nullable=False, server_default="journal_entry")),
            ("subtotal_amount", sa.Column("subtotal_amount", sa.Float(), nullable=True)),
            ("source_module", sa.Column("source_module", sa.String(50), nullable=False, server_default="manual")),
            ("external_id", sa.Column("external_id", sa.String(255), nullable=True)),
            ("idempotency_key", sa.Column("idempotency_key", sa.String(255), nullable=True)),
            ("document_id", sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True)),
            ("dataset_id", sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=True)),
            ("invoice_id", sa.Column("invoice_id", postgresql.UUID(as_uuid=True), nullable=True)),
            (
                "verification_status",
                sa.Column("verification_status", sa.String(50), nullable=False, server_default="confirmed"),
            ),
            (
                "accounting_status",
                sa.Column("accounting_status", sa.String(50), nullable=False, server_default="posted"),
            ),
            ("confidence_score", sa.Column("confidence_score", sa.Float(), nullable=True)),
            ("classification_rationale", sa.Column("classification_rationale", sa.Text(), nullable=True)),
            ("duplicate_fingerprint", sa.Column("duplicate_fingerprint", sa.String(128), nullable=True)),
            ("revision_history", sa.Column("revision_history", sa.JSON(), nullable=False, server_default="[]")),
        ]
        for col_name, col_def in new_tx_cols:
            if col_name not in tx_cols:
                op.add_column("accounting_transactions", col_def)

        for idx_name, cols in [
            ("ix_accounting_transactions_entry_kind", ["entry_kind"]),
            ("ix_accounting_transactions_source_module", ["source_module"]),
            ("ix_accounting_transactions_external_id", ["external_id"]),
            ("ix_accounting_transactions_idempotency_key", ["idempotency_key"]),
            ("ix_accounting_transactions_document_id", ["document_id"]),
            ("ix_accounting_transactions_dataset_id", ["dataset_id"]),
            ("ix_accounting_transactions_invoice_id", ["invoice_id"]),
            ("ix_accounting_transactions_verification_status", ["verification_status"]),
            ("ix_accounting_transactions_accounting_status", ["accounting_status"]),
            ("ix_accounting_transactions_duplicate_fingerprint", ["duplicate_fingerprint"]),
        ]:
            if not _has_index(inspector, "accounting_transactions", idx_name):
                op.create_index(idx_name, "accounting_transactions", cols)

        if not is_sqlite and not _has_unique(
            inspector, "accounting_transactions", "uq_accounting_tx_company_idempotency"
        ):
            op.create_unique_constraint(
                "uq_accounting_tx_company_idempotency",
                "accounting_transactions",
                ["company_id", "idempotency_key"],
            )
        elif is_sqlite and not _has_index(
            inspector, "accounting_transactions", "uq_accounting_tx_company_idempotency"
        ):
            op.create_index(
                "uq_accounting_tx_company_idempotency",
                "accounting_transactions",
                ["company_id", "idempotency_key"],
                unique=True,
            )

    if "accounting_invoices" in tables:
        inv_cols = {col["name"] for col in inspector.get_columns("accounting_invoices")}
        new_inv_cols = [
            ("document_nature", sa.Column("document_nature", sa.String(50), nullable=False, server_default="invoice")),
            ("direction", sa.Column("direction", sa.String(32), nullable=True)),
            ("company_role", sa.Column("company_role", sa.String(50), nullable=True)),
            ("issuer_name", sa.Column("issuer_name", sa.String(255), nullable=True)),
            ("recipient_name", sa.Column("recipient_name", sa.String(255), nullable=True)),
            ("subtotal_amount", sa.Column("subtotal_amount", sa.Float(), nullable=True)),
            ("tax_amount", sa.Column("tax_amount", sa.Float(), nullable=False, server_default="0.0")),
            ("tax_breakdown", sa.Column("tax_breakdown", sa.JSON(), nullable=False, server_default="{}")),
            ("line_items", sa.Column("line_items", sa.JSON(), nullable=False, server_default="[]")),
            ("source_module", sa.Column("source_module", sa.String(50), nullable=False, server_default="manual")),
            ("external_id", sa.Column("external_id", sa.String(255), nullable=True)),
            ("idempotency_key", sa.Column("idempotency_key", sa.String(255), nullable=True)),
            ("document_id", sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True)),
            ("dataset_id", sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=True)),
            ("file_sha256", sa.Column("file_sha256", sa.String(64), nullable=True)),
            ("duplicate_fingerprint", sa.Column("duplicate_fingerprint", sa.String(128), nullable=True)),
            (
                "duplicate_warning",
                sa.Column("duplicate_warning", sa.Boolean(), nullable=False, server_default=sa.false()),
            ),
            ("duplicate_candidates", sa.Column("duplicate_candidates", sa.JSON(), nullable=False, server_default="[]")),
            (
                "verification_status",
                sa.Column("verification_status", sa.String(50), nullable=False, server_default="confirmed"),
            ),
            (
                "accounting_status",
                sa.Column("accounting_status", sa.String(50), nullable=False, server_default="posted"),
            ),
            ("confidence_score", sa.Column("confidence_score", sa.Float(), nullable=True)),
            ("classification_rationale", sa.Column("classification_rationale", sa.Text(), nullable=True)),
            ("revision_history", sa.Column("revision_history", sa.JSON(), nullable=False, server_default="[]")),
            ("extra_data", sa.Column("extra_data", sa.JSON(), nullable=False, server_default="{}")),
        ]
        for col_name, col_def in new_inv_cols:
            if col_name not in inv_cols:
                op.add_column("accounting_invoices", col_def)

        for idx_name, cols in [
            ("ix_accounting_invoices_document_nature", ["document_nature"]),
            ("ix_accounting_invoices_direction", ["direction"]),
            ("ix_accounting_invoices_source_module", ["source_module"]),
            ("ix_accounting_invoices_external_id", ["external_id"]),
            ("ix_accounting_invoices_idempotency_key", ["idempotency_key"]),
            ("ix_accounting_invoices_document_id", ["document_id"]),
            ("ix_accounting_invoices_dataset_id", ["dataset_id"]),
            ("ix_accounting_invoices_file_sha256", ["file_sha256"]),
            ("ix_accounting_invoices_duplicate_fingerprint", ["duplicate_fingerprint"]),
            ("ix_accounting_invoices_verification_status", ["verification_status"]),
            ("ix_accounting_invoices_accounting_status", ["accounting_status"]),
        ]:
            if not _has_index(inspector, "accounting_invoices", idx_name):
                op.create_index(idx_name, "accounting_invoices", cols)

        if not is_sqlite and not _has_unique(
            inspector, "accounting_invoices", "uq_accounting_inv_company_idempotency"
        ):
            op.create_unique_constraint(
                "uq_accounting_inv_company_idempotency",
                "accounting_invoices",
                ["company_id", "idempotency_key"],
            )
        elif is_sqlite and not _has_index(
            inspector, "accounting_invoices", "uq_accounting_inv_company_idempotency"
        ):
            op.create_index(
                "uq_accounting_inv_company_idempotency",
                "accounting_invoices",
                ["company_id", "idempotency_key"],
                unique=True,
            )

    if "accounting_tenant_policies" not in tables:
        op.create_table(
            "accounting_tenant_policies",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "company_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("companies.id", ondelete="CASCADE"),
                nullable=False,
                unique=True,
                index=True,
            ),
            sa.Column(
                "auto_confirm_verified_connector_settlements",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column("confidence_threshold", sa.Float(), nullable=False, server_default="0.85"),
            sa.Column("configured_tax_rules", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("company_aliases", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("extra_config", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    if "accounting_classification_rules" not in tables:
        op.create_table(
            "accounting_classification_rules",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "company_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("companies.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("counterparty_pattern", sa.String(255), nullable=False),
            sa.Column("match_field", sa.String(50), nullable=False, server_default="counterparty"),
            sa.Column("forced_classification", sa.String(50), nullable=False),
            sa.Column("default_category", sa.String(100), nullable=False, server_default="other"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true(), index=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "accounting_classification_rules" in tables:
        op.drop_table("accounting_classification_rules")
    if "accounting_tenant_policies" in tables:
        op.drop_table("accounting_tenant_policies")
