"""add company_onboarding table

Revision ID: 0003_company_onboarding
Revises: 0002_audit_log_indexes
Create Date: 2026-08-24 00:00:00.000000

Ajoute `company_onboarding` (relation 1-1 avec `companies`, clé primaire =
`company_id`) pour le questionnaire d'onboarding post-inscription. Créée
paresseusement par `OnboardingService`, jamais à l'inscription — voir
`backend/app/services/onboarding_service.py`.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0003_company_onboarding"
down_revision: Union[str, None] = "0002_audit_log_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "company_onboarding",
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING", "COMPLETED", "SKIPPED", name="onboarding_status"),
            nullable=False,
        ),
        sa.Column("business_goals", sa.JSON(), nullable=False),
        sa.Column("current_tools", sa.JSON(), nullable=False),
        sa.Column("team_size", sa.String(length=50), nullable=True),
        sa.Column("refined_industry", sa.String(length=120), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("company_id"),
    )


def downgrade() -> None:
    op.drop_table("company_onboarding")
