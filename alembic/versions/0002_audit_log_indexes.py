"""add audit log indexes

Revision ID: 0002_audit_log_indexes
Revises: 0001_baseline_schema
Create Date: 2026-08-21 11:30:00.000000

Migration technique de démonstration (Remédiation post-Phase 34, point 7) :
ajoute deux index de performance sur `audit_log_entries`, utilisés par
`AuditLogService.recent()` (tri par `created_at`) et par les futurs filtres
par tenant (`company_id`). Aucun changement de schéma métier — réversible.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0002_audit_log_indexes"
down_revision: Union[str, None] = "0001_baseline_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        op.f("ix_audit_log_entries_created_at"),
        "audit_log_entries",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_audit_log_entries_company_id"),
        "audit_log_entries",
        ["company_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_audit_log_entries_company_id"), table_name="audit_log_entries")
    op.drop_index(op.f("ix_audit_log_entries_created_at"), table_name="audit_log_entries")
