"""Merge the current production history with the former sandbox revision.

Revision ID: 0036_merge_sandbox_membership_ancestry
Revises: 0035_voice_language_continuity, 0019_company_memberships
"""

revision = "0036_merge_sandbox_membership_ancestry"
down_revision = ("0035_voice_language_continuity", "0019_company_memberships")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass