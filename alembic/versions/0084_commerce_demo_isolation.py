"""Add is_demo column to commerce_connections and normalized_commerce_records, and safely audit legacy demo data.

Revision ID: 0084_commerce_demo_isolation
Revises: 0083_company_display_currency
"""

from alembic import op
import sqlalchemy as sa

revision = "0084_commerce_demo_isolation"
down_revision = "0083_company_display_currency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"
    inspector = sa.inspect(bind)

    # 1. commerce_connections
    conn_cols = {col["name"] for col in inspector.get_columns("commerce_connections")}
    with op.batch_alter_table("commerce_connections") as batch:
        if "is_demo" not in conn_cols:
            batch.add_column(
                sa.Column(
                    "is_demo",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("false" if is_pg else "0"),
                )
            )

    # 2. normalized_commerce_records
    rec_cols = {col["name"] for col in inspector.get_columns("normalized_commerce_records")}
    with op.batch_alter_table("normalized_commerce_records") as batch:
        if "is_demo" not in rec_cols:
            batch.add_column(
                sa.Column(
                    "is_demo",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("false" if is_pg else "0"),
                )
            )

    # 3. Identify and flag legacy synthetic demo data safely without modifying real catalogues
    is_demo_val = "true" if is_pg else "1"
    is_demo_cond = f"is_demo = {is_demo_val}"
    bind.execute(
        sa.text(
            f"UPDATE commerce_connections SET is_demo = {is_demo_val} "
            "WHERE provider IN ('sandbox_demo', 'demo') "
            "OR external_account_id LIKE 'sandbox-demo-%' "
            "OR external_account_id = 'demo_sandbox_store' "
            "OR display_name LIKE '%Démonstration%' "
            "OR display_name LIKE '%Boutique Démo%' "
            "OR display_name LIKE '%Sandbox Demo%'"
        )
    )

    bind.execute(
        sa.text(
            f"UPDATE normalized_commerce_records SET is_demo = {is_demo_val} "
            f"WHERE connection_id IN (SELECT id FROM commerce_connections WHERE {is_demo_cond}) "
            "OR provider IN ('sandbox_demo', 'demo') "
            "OR source_record_id LIKE 'demo_%'"
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("normalized_commerce_records") as batch:
        batch.drop_column("is_demo")

    with op.batch_alter_table("commerce_connections") as batch:
        batch.drop_column("is_demo")
