"""Add explicit owner approval and publishing columns to CRM services.

Revision ID: 0069_crm_service_approval_columns
Revises: 0068_resolve_voice_phone_number_tenant
"""

from alembic import op
import sqlalchemy as sa

revision = "0069_crm_service_approval_columns"
down_revision = "0068_resolve_voice_phone_number_tenant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("crm_services"):
        return

    existing_columns = {col["name"] for col in inspector.get_columns("crm_services")}
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("crm_services")}

    with op.batch_alter_table("crm_services") as batch_op:
        if "is_approved_by_owner" not in existing_columns:
            batch_op.add_column(
                sa.Column(
                    "is_approved_by_owner",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("true"),
                )
            )

        if "is_published" not in existing_columns:
            batch_op.add_column(
                sa.Column(
                    "is_published",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("true"),
                )
            )

    # Data preservation and security rule:
    # Historical demo clinic preset services must NOT be published automatically.
    # Existing standard services remain approved and published.
    op.execute(
        sa.text(
            "UPDATE crm_services SET is_approved_by_owner = false, is_published = false WHERE category = 'clinic'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE crm_services SET is_approved_by_owner = true, is_published = true WHERE category != 'clinic' OR category IS NULL"
        )
    )

    # Add indexes if not present
    if "ix_crm_services_is_approved_by_owner" not in existing_indexes:
        op.create_index(
            "ix_crm_services_is_approved_by_owner",
            "crm_services",
            ["is_approved_by_owner"],
        )

    if "ix_crm_services_is_published" not in existing_indexes:
        op.create_index(
            "ix_crm_services_is_published",
            "crm_services",
            ["is_published"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("crm_services"):
        return

    existing_columns = {col["name"] for col in inspector.get_columns("crm_services")}
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("crm_services")}

    if "ix_crm_services_is_published" in existing_indexes:
        op.drop_index("ix_crm_services_is_published", table_name="crm_services")

    if "ix_crm_services_is_approved_by_owner" in existing_indexes:
        op.drop_index("ix_crm_services_is_approved_by_owner", table_name="crm_services")

    with op.batch_alter_table("crm_services") as batch_op:
        if "is_published" in existing_columns:
            batch_op.drop_column("is_published")

        if "is_approved_by_owner" in existing_columns:
            batch_op.drop_column("is_approved_by_owner")
